"""Abaqus-side socket agent.

This file intentionally uses only the Python standard library so it can run
inside Abaqus 2024's bundled Python 3.10 without installing project deps there.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import platform
import socketserver
import sys
import threading
import traceback
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 48152

_GLOBALS: dict[str, Any] = {
    "__name__": "__abaqus_mcp_exec__",
    "__doc__": None,
}
_EXEC_LOCK = threading.Lock()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return {
            "repr": repr(value),
            "type": f"{type(value).__module__}.{type(value).__name__}",
        }


def _node_source(node: ast.AST) -> str | None:
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _key_literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Index):  # pragma: no cover - compatibility for older ASTs
        return _key_literal(node.value)
    return None


def _find_subscript_parent(code: str, missing_key: Any) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _key_literal(node.slice) == missing_key:
            return _node_source(node.value)
    return None


def _format_execution_error(code: str, exc: BaseException) -> dict[str, Any]:
    tb_str = traceback.format_exc()
    tb_lines = [l for l in tb_str.strip().splitlines() if l.strip()]
    core_error = tb_lines[-1] if tb_lines else str(exc)
    error_type = f"{type(exc).__module__}.{type(exc).__name__}"

    if isinstance(exc, KeyError):
        missing_key = exc.args[0] if exc.args else None
        parent_path = _find_subscript_parent(code, missing_key)
        inspect_target = parent_path or "<parent object>"
        suggestion = (
            "Dictionary key not found. [MANDATORY ACTION]: "
            "Extract the parent dictionary path and call `abaqus_inspect_object` "
            "on %s to check valid keys."
        ) % inspect_target
        recovery = {
            "missing_key": _jsonable(missing_key),
            "inspect_object_path": parent_path,
            "suggested_tool": "abaqus_inspect_object",
        }
    elif isinstance(exc, AttributeError):
        missing_attr = getattr(exc, "name", None)
        source_obj = getattr(exc, "obj", None)
        object_type = type(source_obj).__name__ if source_obj is not None else None
        attr_text = " %r" % missing_attr if missing_attr else ""
        suggestion = (
            "Method/attribute not found. [MANDATORY ACTION]: "
            "Extract the object path and call `abaqus_inspect_object` "
            "to check valid methods and attributes."
        )
        recovery = {
            "missing_attribute": missing_attr,
            "object_type": object_type,
            "suggested_tool": "abaqus_inspect_object",
        }
    elif isinstance(exc, NameError):
        suggestion = (
            "Variable undefined. Check imports "
            "(e.g., `from abaqus import *` or `from abaqusConstants import *`)."
        )
        recovery = {"suggested_fix": "Add missing import statement."}
    elif isinstance(exc, TypeError):
        suggestion = (
            "Invalid parameter type. Review standard Abaqus API arguments."
        )
        recovery = {"suggested_fix": "Check argument types against the Abaqus Python API reference."}
    elif isinstance(exc, RuntimeError):
        suggestion = (
            "Underlying failure. Read the core_error carefully. "
            "Verify geometry/mesh prerequisites. If unsure of object state, "
            "use `abaqus_inspect_object`."
        )
        recovery = {"suggested_tool": "abaqus_inspect_object"}
    else:
        suggestion = (
            "Unexpected error. Read the full_traceback for details. "
            "If unsure of object state, use `abaqus_inspect_object`."
        )
        recovery = {"suggested_tool": "abaqus_inspect_object"}

    return {
        "ok": False,
        "core_error": core_error,
        "action_suggestion": suggestion,
        "full_traceback": tb_str,
        "error": core_error,
        "error_type": error_type,
        "recovery": recovery,
    }


def _read_message(request: socketserver.BaseRequestHandler) -> dict[str, Any]:
    chunks: list[bytes] = []
    while True:
        chunk = request.request.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed before a complete message was received")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
    message = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(message, dict):
        raise RuntimeError("protocol message must be a JSON object")
    return message


def _send_message(request: socketserver.BaseRequestHandler, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request.request.sendall(data + b"\n")


def _execute(code: str) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = _GLOBALS
    returned = None
    mode = "exec"

    try:
        from abaqus import mdb, session  # type: ignore
    except Exception:
        pass
    else:
        namespace.update({"mdb": mdb, "session": session})

    with _EXEC_LOCK, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            try:
                parsed = ast.parse(code, mode="eval")
            except SyntaxError:
                parsed = ast.parse(code, mode="exec")
                compiled = compile(parsed, "<abaqus-mcp>", "exec")
                exec(compiled, namespace, namespace)
                returned = namespace.get("result")
            else:
                mode = "eval"
                compiled = compile(parsed, "<abaqus-mcp>", "eval")
                returned = eval(compiled, namespace, namespace)
        except Exception as exc:
            response = _format_execution_error(code, exc)
            response.update(
                {
                    "mode": mode,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                }
            )
            return response

    return {
        "mode": mode,
        "ok": True,
        "return_value": _jsonable(returned),
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def _ping() -> dict[str, Any]:
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "thread": threading.current_thread().name,
    }


class AbaqusMcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        request_id = None
        try:
            message = _read_message(self)
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params") or {}

            if method == "ping":
                result = _ping()
            elif method == "execute":
                code = params.get("code")
                if not isinstance(code, str) or not code.strip():
                    raise ValueError("params.code must be a non-empty string")
                result = _execute(code)
            else:
                raise ValueError(f"unknown method: {method!r}")

            _send_message(self, {"id": request_id, "ok": True, "result": result})
        except Exception as exc:
            _send_message(
                self,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "message": str(exc),
                        "type": f"{type(exc).__module__}.{type(exc).__name__}",
                        "traceback": traceback.format_exc(),
                    },
                },
            )


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = False
    daemon_threads = True


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    with ThreadedTCPServer((host, port), AbaqusMcpHandler) as server:
        print("Abaqus MCP agent listening on %s:%s" % (host, port))
        server.serve_forever()


def start_background(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadedTCPServer:
    server = ThreadedTCPServer((host, port), AbaqusMcpHandler)
    thread = threading.Thread(target=server.serve_forever, name="AbaqusMcpAgent", daemon=True)
    thread.start()
    print("Abaqus MCP agent listening on %s:%s in background" % (host, port))
    return server


if __name__ == "__main__":
    serve()
