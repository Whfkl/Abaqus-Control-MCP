"""Abaqus-side socket agent.

This file intentionally uses only the Python standard library so it can run
inside Abaqus 2024's bundled Python 3.10 without installing project deps there.
"""

from __future__ import annotations

import ast
import contextlib
import difflib
import io
import inspect
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


def _extract_tb_lineno(exc: BaseException) -> int | None:
    """Extract the line number where the exception was raised from its traceback."""
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<abaqus-mcp>":
            return tb.tb_lineno
        tb = tb.tb_next
    return None


def _find_subscript_parent(code: str, missing_key: Any, lineno: int | None = None) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    candidates: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _key_literal(node.slice) == missing_key:
            src = _node_source(node.value)
            if src is not None:
                candidates.append((getattr(node, "lineno", 0), src))
    if not candidates:
        return None
    if lineno is not None:
        candidates.sort(key=lambda c: abs(c[0] - lineno))
    return candidates[0][1]


def _find_attribute_parent(code: str, missing_attr: str) -> str | None:
    """Find the object that was expected to have *missing_attr* via AST analysis."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == missing_attr:
            return _node_source(node.value)
    return None


def _extract_func_name(exc: BaseException) -> str | None:
    """Extract function/method name from a TypeError message."""
    import re
    msg = str(exc)
    m = re.search(r"([\w.]+)\(\)", msg)
    if m:
        return m.group(1)
    m = re.search(r"'([\w.]+)'", msg)
    if m:
        return m.group(1)
    return None


def _extract_code_excerpt(code: str, lineno: int | None, radius: int = 2) -> str | None:
    if lineno is None:
        return None
    lines = code.splitlines()
    if not lines:
        return None
    index = max(0, lineno - 1)
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    excerpt_lines: list[str] = []
    for i in range(start, end):
        prefix = ">>" if i == index else "  "
        excerpt_lines.append("%s %4d | %s" % (prefix, i + 1, lines[i]))
    return "\n".join(excerpt_lines)


def _resolve_simple_expr(expr: str, namespace: dict[str, Any]) -> Any:
    """Resolve simple name/attribute/subscript expressions without executing calls."""

    def _eval_node(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            return namespace[node.id]
        if isinstance(node, ast.Attribute):
            return getattr(_eval_node(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            base = _eval_node(node.value)
            key = ast.literal_eval(node.slice)
            return base[key]
        raise ValueError("unsupported expression node")

    parsed = ast.parse(expr, mode="eval")
    return _eval_node(parsed.body)


def _extract_call_target(code: str, lineno: int | None) -> str | None:
    if lineno is None:
        return None
    try:
        lines = code.splitlines()
        if lineno - 1 < 0 or lineno - 1 >= len(lines):
            return None
        node = ast.parse(lines[lineno - 1], mode="exec")
    except Exception:
        return None
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            return _node_source(item.func)
    return None


def _summarize_mapping_keys(mapping_obj: Any, missing_key: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available_keys_sample": [],
        "possible_keys": [],
    }
    keys_method = getattr(mapping_obj, "keys", None)
    if not callable(keys_method):
        return result
    try:
        scanned_keys = list(keys_method())
    except Exception:
        return result

    key_texts = [str(k) for k in scanned_keys]
    result["available_keys_sample"] = key_texts

    if missing_key is not None:
        try:
            near = difflib.get_close_matches(str(missing_key), key_texts, n=8, cutoff=0.45)
            result["possible_keys"] = near
        except Exception:
            pass
    return result


def _summarize_object_members(obj: Any, missing_attr: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "possible_members": [],
    }
    try:
        members = sorted([name for name in dir(obj) if not name.startswith("_")])
    except Exception:
        return result

    if missing_attr:
        try:
            result["possible_members"] = difflib.get_close_matches(missing_attr, members, n=10, cutoff=0.45)
        except Exception:
            pass
    return result


def _summarize_callable(target_expr: str | None, namespace: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "call_target": target_expr,
        "callable_doc_excerpt": None,
    }
    if not target_expr:
        return summary
    try:
        target = _resolve_simple_expr(target_expr, namespace)
    except Exception:
        return summary

    try:
        doc = inspect.getdoc(target) or ""
        summary["callable_doc_excerpt"] = doc[:400] if doc else None
    except Exception:
        summary["callable_doc_excerpt"] = None
    return summary


def _format_execution_error(code: str, exc: BaseException, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    tb_str = traceback.format_exc()
    tb_lines = [l for l in tb_str.strip().splitlines() if l.strip()]
    core_error = tb_lines[-1] if tb_lines else str(exc)
    error_type = f"{type(exc).__module__}.{type(exc).__name__}"
    lineno = _extract_tb_lineno(exc)
    code_excerpt = _extract_code_excerpt(code, lineno)

    if isinstance(exc, KeyError):
        missing_key = exc.args[0] if exc.args else None
        parent_path = _find_subscript_parent(code, missing_key, lineno)
        recovery: dict[str, Any] = {
            "missing_key": _jsonable(missing_key),
            "parent_object_path": parent_path,
        }
        if parent_path and namespace is not None:
            try:
                parent_obj = _resolve_simple_expr(parent_path, namespace)
                recovery.update(_summarize_mapping_keys(parent_obj, missing_key))
            except Exception:
                pass
    elif isinstance(exc, AttributeError):
        missing_attr = getattr(exc, "name", None)
        source_obj = getattr(exc, "obj", None)
        object_type = type(source_obj).__name__ if source_obj is not None else None
        parent_path = _find_attribute_parent(code, missing_attr) if missing_attr else None
        recovery = {
            "missing_attribute": missing_attr,
            "object_type": object_type,
            "parent_object_path": parent_path,
        }
        if source_obj is not None:
            try:
                recovery.update(_summarize_object_members(source_obj, missing_attr))
            except Exception:
                pass
    elif isinstance(exc, NameError):
        recovery = {"missing_variable": getattr(exc, "name", None)}
    elif isinstance(exc, TypeError):
        call_target = _extract_call_target(code, lineno)
        recovery = {"call_target": call_target}
        if namespace is not None:
            recovery.update(_summarize_callable(call_target, namespace))
    else:
        recovery = {}

    return {
        "ok": False,
        "core_error": core_error,
        "error_type": error_type,
        "error_line": lineno,
        "code_excerpt": code_excerpt,
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
            response = _format_execution_error(code, exc, namespace)
            return response

    return {
        "ok": True,
        "return_value": _jsonable(returned),
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
    allow_reuse_address = True
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
