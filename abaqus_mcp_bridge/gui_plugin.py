"""Abaqus/CAE GUI-side MCP bridge plugin.

This file is packaged so the installer can copy it into the Abaqus plugin
search directory without requiring a source checkout.
"""

from abaqusGui import (
    AFXForm,
    FXMAPFUNC,
    SEL_COMMAND,
    SEL_TIMEOUT,
    getAFXApp,
    sendCommand,
    showAFXErrorDialog,
)
import base64
import json
import os
import platform
import queue
import socketserver
import sys
import tempfile
import threading
import time
import traceback
import uuid

HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
LOG_PATH = os.path.join(tempfile.gettempdir(), "abaqus_mcp_gui_plugin.log")


def _log(message):
    try:
        with open(LOG_PATH, "a") as handle:
            handle.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _announce(message):
    print(message)
    try:
        main_window = getAFXApp().getAFXMainWindow()
        if hasattr(main_window, "writeToMessageArea"):
            main_window.writeToMessageArea(message)
    except Exception:
        pass


def _send(sock, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")


def _recv(sock):
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed before a complete message was received")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


def _kernel_wrapper(code, response_path):
    encoded_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
    encoded_path = base64.b64encode(response_path.encode("utf-8")).decode("ascii")
    template = r'''
import ast
import base64
import contextlib
import io
import json
import os
import sys
import traceback

code = base64.b64decode("__ABAQUS_MCP_CODE__").decode("utf-8")
response_path = base64.b64decode("__ABAQUS_MCP_RESPONSE__").decode("utf-8")

def _jsonable(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return {
            "repr": repr(value),
            "type": "%s.%s" % (type(value).__module__, type(value).__name__),
        }

def _node_source(node):
    try:
        return ast.unparse(node)
    except Exception:
        return None

def _key_literal(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Index):
        return _key_literal(node.value)
    return None

def _extract_tb_lineno(exc):
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<abaqus-mcp>":
            return tb.tb_lineno
        tb = tb.tb_next
    return None

def _find_subscript_parent(source, missing_key, lineno=None):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    candidates = []
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

def _find_attribute_parent(source, missing_attr):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == missing_attr:
            return _node_source(node.value)
    return None

def _extract_func_name(exc):
    import re
    msg = str(exc)
    m = re.search(r"([\w.]+)\(\)", msg)
    if m:
        return m.group(1)
    m = re.search(r"'([\w.]+)'", msg)
    if m:
        return m.group(1)
    return None

def _build_search_queries(exc, source, abaqus_version=""):
    import re as _re
    queries = []
    base = "Abaqus Python API"
    if isinstance(exc, AttributeError):
        attr = getattr(exc, "name", "") or ""
        obj_type = type(getattr(exc, "obj", "")).__name__
        if attr:
            queries.append("%s %s %s method" % (base, obj_type, attr))
            queries.append("abaqus %s python scripting %s" % (obj_type, attr))
    elif isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else ""
        queries.append("%s key name %s" % (base, key))
        queries.append("abaqus dictionary key naming convention")
    elif isinstance(exc, NameError):
        name = getattr(exc, "name", "") or ""
        if name:
            queries.append("%s %s import" % (base, name))
            queries.append("abaqus python %s undefined" % name)
    elif isinstance(exc, TypeError):
        func = _extract_func_name(exc)
        if func:
            queries.append("%s %s signature parameters" % (base, func))
            queries.append("abaqus %s arguments" % func)
    queries.append("%s scripting guide" % base)
    if abaqus_version:
        queries = [q + " " + abaqus_version for q in queries]
    return queries

def _get_abaqus_version():
    try:
        ver = getattr(session, "version", None)
        if ver:
            return "Abaqus " + str(ver)
    except Exception:
        pass
    return ""

def _format_execution_error(source, exc):
    tb_str = traceback.format_exc()
    tb_lines = [l for l in tb_str.strip().splitlines() if l.strip()]
    core_error = tb_lines[-1] if tb_lines else str(exc)
    error_type = "%s.%s" % (type(exc).__module__, type(exc).__name__)
    abaqus_version = _get_abaqus_version()
    lineno = _extract_tb_lineno(exc)

    if isinstance(exc, KeyError):
        missing_key = exc.args[0] if exc.args else None
        parent_path = _find_subscript_parent(source, missing_key, lineno)
        inspect_target = parent_path or "<parent object>"
        suggestion = (
            "Dictionary key not found. [MANDATORY ACTION]: "
            "Extract the parent dictionary path and call `inspect` "
            "on %s to check valid keys."
        ) % inspect_target
        recovery = {
            "missing_key": _jsonable(missing_key),
            "inspect_object_path": parent_path,
            "suggested_tool": "inspect",
        }
    elif isinstance(exc, AttributeError):
        missing_attr = getattr(exc, "name", None)
        source_obj = getattr(exc, "obj", None)
        object_type = type(source_obj).__name__ if source_obj is not None else None
        parent_path = _find_attribute_parent(source, missing_attr) if missing_attr else None
        if parent_path:
            suggestion = (
                "Method/attribute '%s' not found. [MANDATORY ACTION]: "
                "Call `inspect` on %s to check valid methods and attributes."
            ) % (missing_attr, parent_path)
        else:
            suggestion = (
                "Method/attribute '%s' not found. [MANDATORY ACTION]: "
                "Extract the object path and call `inspect` "
                "to check valid methods and attributes."
            ) % (missing_attr or "<unknown>")
        recovery = {
            "missing_attribute": missing_attr,
            "object_type": object_type,
            "inspect_object_path": parent_path,
            "suggested_tool": "inspect",
        }
    elif isinstance(exc, NameError):
        missing_name = getattr(exc, "name", None)
        suggestion = (
            "Variable '%s' undefined. Check imports "
            "(e.g., `from abaqus import *` or `from abaqusConstants import *`)."
        ) % (missing_name or "<unknown>")
        recovery = {
            "missing_variable": missing_name,
            "suggested_fix": "Add missing import or define the variable.",
            "suggested_tool": "inspect",
        }
    elif isinstance(exc, TypeError):
        func_name = _extract_func_name(exc)
        if func_name:
            suggestion = (
                "Invalid arguments for '%s'. Review its parameter types "
                "in the Abaqus Python API."
            ) % func_name
        else:
            suggestion = (
                "Invalid parameter type. Review standard Abaqus API arguments."
            )
        recovery = {
            "function": func_name,
            "suggested_fix": "Check argument types against the Abaqus Python API reference.",
            "suggested_tool": "inspect",
        }
    elif isinstance(exc, RuntimeError):
        suggestion = (
            "Underlying failure. Read the core_error carefully. "
            "Verify geometry/mesh prerequisites. If unsure of object state, "
            "use `inspect`."
        )
        recovery = {"suggested_tool": "inspect"}
    else:
        suggestion = (
            "Unexpected error. Read the full_traceback for details. "
            "If unsure of object state, use `inspect`."
        )
        recovery = {"suggested_tool": "inspect"}

    recovery["search_queries"] = _build_search_queries(exc, source, abaqus_version)
    recovery["search_hint"] = (
        "If inspection alone is insufficient, search the web for the queries above "
        "to find the correct Abaqus API usage, method signatures, or naming conventions."
    )

    return {
        "ok": False,
        "core_error": core_error,
        "action_suggestion": suggestion,
        "full_traceback": tb_str,
        "submitted_code": source[:2000],
        "error": core_error,
        "error_type": error_type,
        "recovery": recovery,
    }

namespace = globals().setdefault("_ABAQUS_MCP_GLOBALS", {
    "__name__": "__abaqus_mcp_exec__",
    "__doc__": None,
})
namespace.update({
    "mdb": globals().get("mdb"),
    "session": globals().get("session"),
})

stdout = io.StringIO()
stderr = io.StringIO()
returned = None
mode = "exec"
payload = None

try:
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
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
            returned_error = _format_execution_error(code, exc)
            returned_error.update({
                "mode": mode,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
            })
            payload = {
                "ok": True,
                "result": returned_error,
            }

    if payload is None:
        payload = {
            "ok": True,
            "result": {
                "mode": mode,
                "ok": True,
                "return_value": _jsonable(returned),
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
            },
        }
except Exception as exc:
    payload = {
        "ok": True,
        "result": dict(
            _format_execution_error(code, exc),
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        ),
    }

with open(response_path, "w") as handle:
    json.dump(payload, handle, ensure_ascii=False)
'''
    return (
        template.replace("__ABAQUS_MCP_CODE__", encoded_code)
        .replace("__ABAQUS_MCP_RESPONSE__", encoded_path)
    )


def _run_kernel_code(code, timeout):
    response_path = os.path.join(
        tempfile.gettempdir(), "abaqus_mcp_%s.json" % uuid.uuid4().hex
    )
    command = _kernel_wrapper(code, response_path)
    _log("sendCommand start response_path=%s" % response_path)
    sendCommand(command, False, False)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(response_path):
            with open(response_path, "r") as handle:
                payload = json.load(handle)
            try:
                os.remove(response_path)
            except Exception:
                pass
            if not payload.get("ok"):
                error = payload.get("error", {})
                _log("kernel error: %s" % error.get("message", "kernel command failed"))
                raise RuntimeError(error.get("message", "kernel command failed"))
            _log("kernel response ok")
            return payload["result"]
        time.sleep(0.05)

    raise TimeoutError("timed out waiting for Abaqus kernel response")


class McpGuiHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request_id = None
        try:
            message = _recv(self.request)
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params") or {}
            _log("request method=%s id=%s" % (method, request_id))

            if _DISPATCHER is None:
                raise RuntimeError("GUI dispatcher is not initialized")

            wait_timeout = float(params.get("timeout") or os.environ.get("ABAQUS_MCP_TIMEOUT", "60")) + 5.0
            item = GuiRequest(method, params)
            _REQUESTS.put(item)
            _log("queued method=%s id=%s" % (method, request_id))

            if not item.event.wait(wait_timeout):
                raise TimeoutError("timed out waiting for GUI dispatcher")
            if item.error is not None:
                raise item.error
            result = item.result

            _send(self.request, {"id": request_id, "ok": True, "result": result})
            _log("response ok id=%s" % request_id)
        except Exception as exc:
            _log("response error id=%s error=%s" % (request_id, exc))
            _send(
                self.request,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "message": str(exc),
                        "type": "%s.%s" % (type(exc).__module__, type(exc).__name__),
                        "traceback": traceback.format_exc(),
                    },
                },
            )


class McpGuiServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


_SERVER = None
_DISPATCHER = None
_REQUESTS = queue.Queue()


class GuiRequest:
    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.event = threading.Event()
        self.result = None
        self.error = None


def _handle_on_gui_thread(item):
    method = item.method
    params = item.params
    timeout = float(params.get("timeout") or os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))

    if method == "ping":
        code = (
            "import os, sys, platform\n"
            "from abaqus import mdb, session\n"
            "result = {'python': sys.version, 'executable': sys.executable, "
            "'platform': platform.platform(), 'pid': os.getpid(), "
            "'cpu_count': os.cpu_count(), "
            "'abaqus_version': getattr(session, 'version', None), "
            "'models': list(mdb.models.keys()), "
            "'viewports': list(session.viewports.keys())}"
        )
        result = _run_kernel_code(code, timeout)
        result = result["return_value"]
        result["guiProcess"] = {
            "python": sys.version,
            "platform": platform.platform(),
            "thread": threading.current_thread().name,
        }
        return result

    if method == "execute":
        code = params.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("params.code must be a non-empty string")
        return _run_kernel_code(code, timeout)

    raise ValueError("unknown method: %r" % method)


def start_gui_agent():
    global _SERVER
    if _SERVER is not None:
        _log("start requested, already running")
        return "Abaqus MCP GUI agent is already running on %s:%s" % (HOST, PORT)
    _log("starting GUI agent on %s:%s" % (HOST, PORT))
    _SERVER = McpGuiServer((HOST, PORT), McpGuiHandler)
    thread = threading.Thread(target=_SERVER.serve_forever, name="AbaqusMcpGuiAgent")
    thread.daemon = True
    thread.start()
    _log("started GUI agent")
    return "Abaqus MCP GUI agent listening on %s:%s" % (HOST, PORT)


def stop_gui_agent():
    global _SERVER
    if _SERVER is None:
        return "Abaqus MCP GUI agent is not running."
    try:
        _SERVER.shutdown()
        _SERVER.server_close()
    finally:
        _SERVER = None
    _log("stopped GUI agent")
    return "Abaqus MCP GUI agent stopped."


class McpGuiActionForm(AFXForm):
    ID_START = AFXForm.ID_LAST + 1
    ID_STOP = AFXForm.ID_LAST + 2
    ID_POLL = AFXForm.ID_LAST + 3

    def __init__(self, owner, action):
        global _DISPATCHER
        AFXForm.__init__(self, owner)
        self.action = action
        FXMAPFUNC(self, SEL_COMMAND, self.ID_START, McpGuiActionForm.onCmdStart)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_STOP, McpGuiActionForm.onCmdStop)
        FXMAPFUNC(self, SEL_TIMEOUT, self.ID_POLL, McpGuiActionForm.onTimeout)
        _DISPATCHER = self

    def getFirstDialog(self):
        if self.action == "start":
            self.onCmdStart(None, None, None)
        elif self.action == "stop":
            self.onCmdStop(None, None, None)
        return None

    def _schedule_poll(self):
        getAFXApp().addTimeout(100, self, self.ID_POLL)

    def onTimeout(self, sender, sel, ptr):
        processed = 0
        while processed < 5:
            try:
                item = _REQUESTS.get_nowait()
            except queue.Empty:
                break
            try:
                _log("GUI thread handling method=%s" % item.method)
                item.result = _handle_on_gui_thread(item)
                _log("GUI thread handled method=%s" % item.method)
            except Exception as exc:
                item.error = exc
                _log("GUI thread error method=%s error=%s" % (item.method, exc))
            finally:
                item.event.set()
            processed += 1

        if _SERVER is not None:
            self._schedule_poll()
        return 1

    def onCmdStart(self, sender, sel, ptr):
        try:
            message = start_gui_agent()
            self._schedule_poll()
            _announce(message)
            _announce("Abaqus MCP GUI plugin log: %s" % LOG_PATH)
        except Exception as exc:
            message = "Abaqus MCP GUI agent failed: %s" % exc
            _log(message)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), message)
        return 1

    def onCmdStop(self, sender, sel, ptr):
        try:
            message = stop_gui_agent()
            _announce(message)
        except Exception as exc:
            message = "Abaqus MCP GUI agent stop failed: %s" % exc
            _log(message)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), message)
        return 1

toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
toolset.registerGuiMenuButton(
    object=McpGuiActionForm(toolset, "start"),
    buttonText="Abaqus-Control-MCP|Start MCP Bridge",
    version="0.1.0",
    author="Codex",
    applicableModules=["Part", "Property", "Assembly", "Step", "Interaction", "Load", "Mesh", "Job", "Visualization"],
    description="Start the TCP bridge for the active Abaqus/CAE session.",
)
toolset.registerGuiMenuButton(
    object=McpGuiActionForm(toolset, "stop"),
    buttonText="Abaqus-Control-MCP|Stop MCP Bridge",
    version="0.1.0",
    author="Codex",
    applicableModules=["Part", "Property", "Assembly", "Step", "Interaction", "Load", "Mesh", "Job", "Visualization"],
    description="Stop the TCP bridge.",
)
