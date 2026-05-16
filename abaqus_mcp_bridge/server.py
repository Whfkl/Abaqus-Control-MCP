"""MCP stdio server that forwards Python execution requests to Abaqus.

Core tools: ping, run_python, inspect — plus viewport capture and ODB metadata
as helpers that are awkward to replicate with raw Python. Everything else
(model creation, job submission, field output extraction) goes through run_python.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP

from .client import AbaqusBridgeClient


def _ensure_gui_plugin() -> None:
    """Install the GUI plugin silently if not already present."""
    try:
        import shutil
        from importlib import resources
        from pathlib import Path

        target_dir = Path(os.environ.get("ABAQUS_MCP_PLUGIN_DIR", Path.home() / "abaqus_plugins"))
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "abaqus_mcp_gui_plugin.py"

        source = resources.files("abaqus_mcp_bridge").joinpath("gui_plugin.py")
        with resources.as_file(source) as src:
            if target.exists() and target.read_bytes() == Path(src).read_bytes():
                return
            shutil.copy2(src, target)
    except Exception:
        pass


_ensure_gui_plugin()


DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))

INSTRUCTIONS = """You are controlling a live Abaqus/CAE session via MCP tools.

MANDATORY RULES:
1. INTENT DECLARATION: Before every run_python call, output a sentence: "I will now [action] to [purpose]."
2. CHUNKING: Never write the full script at once. Execute in stages: (A) Geometry & Mesh → (B) Materials & Sections → (C) Assembly & Steps → (D) Loads & BCs. Pause after each, summarize, and ask the user: "Should I proceed to the next stage?"
3. NO GUESSING: If unsure about any Abaqus API method, attribute, or key — call inspect first. Never guess.
4. GEOMETRY GRABBING (NO findAt): NEVER use `findAt()`. Immediately after creating a feature (Extrude/Cut), grab the geometry using robust methods (getByBoundingBox, getByBoundingCylinder, or topology filtering) and wrap it into a named Set/Surface IMMEDIATELY. All subsequent steps MUST reference these semantic names.
5. ERROR RECOVERY: When run_python returns "ok": False, read core_error and action_suggestion, call inspect if suggested, rewrite based on facts — no apology, no filler.
6. WEB-ASSISTED RECOVERY: If the `search_queries` field is present in the recovery metadata and inspection alone is insufficient, use web search with those queries (include the Abaqus version) to find the correct API usage, method signatures, or naming conventions. Combine documentation findings with local inspection results.
7. WORKING DIRECTORY: Before building a new model, ask the user if they want to change the working directory.
CODE CONVENTIONS: Use `from abaqus import *` and `from abaqusConstants import *`. Set `result = {...}` to return data. Always wrap in try/except."""

mcp = FastMCP("abaqus-control-mcp", instructions=INSTRUCTIONS)


def _client(timeout: float | None = None) -> AbaqusBridgeClient:
    return AbaqusBridgeClient(
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT,
    )


_VIEWPORT_CODE_TEMPLATE = r"""
import os, tempfile, base64
from abaqus import session

vp_name = __VP__
fmt = __FMT__

result = {}
try:
    if not vp_name or vp_name not in session.viewports.keys():
        vp_name = session.currentViewportName
    vp = session.viewports[vp_name]
    tmp = tempfile.NamedTemporaryFile(suffix='.' + fmt.lower(), delete=False)
    tmp.close()
    vp.view.print(filename=tmp.name, format=fmt.upper(), options='')
    with open(tmp.name, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    os.unlink(tmp.name)
    result = {
        'success': True,
        'viewport': vp_name,
        'format': fmt.lower(),
        'image_base64': b64,
        'size_bytes': len(b64) * 3 // 4,
    }
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
"""


# ---------------------------------------------------------------------------
# Generic python execution wrapper
# ---------------------------------------------------------------------------


async def _exec(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code in Abaqus and return the result dict."""
    return await anyio.to_thread.run_sync(_client(timeout).execute, code)


def _inspect_code(object_path: str, depth: int = 1) -> str:
    """Build Abaqus-side code for introspecting an object path."""
    depth = max(1, min(depth, 3))
    return r"""
from abaqus import mdb, session

object_path = __OBJECT_PATH__
max_depth = __DEPTH__

def _jsonable_key(key):
    try:
        import json
        json.dumps(key, ensure_ascii=False)
        return key
    except Exception:
        return repr(key)

def _safe_repr(val):
    try:
        r = repr(val)
        return r[:200] if len(r) > 200 else r
    except Exception:
        return "<%s>" % type(val).__name__

def _inspect_one(obj, current_depth):
    keys_method = getattr(obj, "keys", None)
    if callable(keys_method):
        info = {
            "kind": "mapping",
            "type": type(obj).__name__,
            "keys": [_jsonable_key(key) for key in keys_method()],
        }
        if current_depth < max_depth:
            children = {}
            for key in list(keys_method())[:20]:
                try:
                    child = obj[key]
                    children[_jsonable_key(key)] = _inspect_one(child, current_depth + 1)
                except Exception as e:
                    children[_jsonable_key(key)] = {"error": str(e)}
            info["children"] = children
        return info
    else:
        attrs = [name for name in dir(obj) if not name.startswith("_")]
        info = {
            "kind": "object",
            "type": type(obj).__name__,
            "attributes": attrs,
        }
        if current_depth < max_depth:
            children = {}
            for attr in attrs[:20]:
                try:
                    child = getattr(obj, attr)
                    if callable(child):
                        children[attr] = {"kind": "callable", "type": type(child).__name__}
                    else:
                        children[attr] = _inspect_one(child, current_depth + 1)
                except Exception as e:
                    children[attr] = {"error": str(e)}
            info["children"] = children
        return info

try:
    obj = eval(object_path, {"__builtins__": {}}, {"mdb": mdb, "session": session})
    info = _inspect_one(obj, 1)
    info["ok"] = True
    info["object_path"] = object_path
    result = info
except Exception as exc:
    result = {
        "ok": False,
        "object_path": object_path,
        "error": "Inspection failed for %r: %s: %s" % (
            object_path,
            type(exc).__name__,
            str(exc),
        ),
    }
""".replace("__OBJECT_PATH__", json.dumps(object_path)).replace("__DEPTH__", str(depth))


# ---------------------------------------------------------------------------
# Core tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def ping(timeout: float | None = None) -> dict[str, Any]:
    """Check whether the Abaqus-side bridge agent is reachable.

    Returns session state including Python version, platform, PID, CPU count,
    models, and viewports.
    """
    return await _exec(
        "from abaqus import mdb, session\n"
        "import os, sys, platform\n"
        "result = {\n"
        "  'python': sys.version,\n"
        "  'executable': sys.executable,\n"
        "  'platform': platform.platform(),\n"
        "  'pid': os.getpid(),\n"
        "  'cpu_count': os.cpu_count(),\n"
        "  'abaqus_version': getattr(session, 'version', None),\n"
        "  'models': list(mdb.models.keys()),\n"
        "  'viewports': list(session.viewports.keys()),\n"
        "}",
        timeout,
    )


@mcp.tool()
async def run_python(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code in the active Abaqus/CAE kernel.

    Single-line expressions are evaluated and their value returned.
    Multi-line code is executed; set a variable named ``result`` to return data.
    Stdout, stderr, and any error details are included in the response.
    """
    if not code.strip():
        raise ValueError("code must not be empty")
    return await _exec(code, timeout)


@mcp.tool()
async def inspect(object_path: str, depth: int = 1, timeout: float | None = None) -> dict[str, Any]:
    """Inspect an Abaqus object path and return available keys or public attributes.

    Args:
        object_path: Python expression evaluating to an Abaqus object.
        depth: How many levels deep to inspect (1-3, default 1). depth=2 shows
            child objects inline, reducing the number of follow-up inspect calls.

    Examples:
        - ``mdb.models['Model-1'].parts``
        - ``session.viewports``
        - ``mdb.models['Model-1'].rootAssembly``
    """
    if not object_path.strip():
        raise ValueError("object_path must not be empty")
    return await _exec(_inspect_code(object_path.strip(), depth), timeout)


@mcp.tool()
async def set_workdir(path: str, timeout: float | None = None) -> dict[str, Any]:
    """Change the Abaqus working directory.

    Args:
        path: Absolute path to set as the working directory.
    Returns the previous and new working directory.
    """
    if not path.strip():
        raise ValueError("path must not be empty")
    code = r"""
import os

new_path = __PATH__

result = {}
try:
    old_dir = os.getcwd()
    if not os.path.isdir(new_path):
        result = {'success': False, 'error': 'Directory does not exist: ' + new_path}
    else:
        os.chdir(new_path)
        result = {'success': True, 'previous': old_dir, 'current': os.getcwd()}
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
""".replace("__PATH__", json.dumps(path.strip()))
    return await _exec(code, timeout)


@mcp.tool()
async def list_jobs(timeout: float | None = None) -> dict[str, Any]:
    """List all analysis jobs defined in the current Abaqus session with their status."""
    code = r"""
from abaqus import mdb
jobs = []
for name in mdb.jobs.keys():
    job = mdb.jobs[name]
    j = {'name': name}
    for attr in ('status', 'type', 'model', 'description', 'numCpus', 'numDomains', 'memory', 'explicitPrecision'):
        try:
            val = getattr(job, attr, None)
            if val is not None:
                j[attr] = str(val)
        except Exception:
            pass
    jobs.append(j)
result = {'jobs': jobs}
"""
    return await _exec(code, timeout)


@mcp.tool()
async def get_odb_info(odb_path: str, timeout: float | None = None) -> dict[str, Any]:
    """Open an ODB file (read-only) and return its metadata.

    Returns steps (with frame count and total time), parts, instances, section points,
    and available field/history output variables.
    """
    code = r"""
from abaqus import mdb
from odbAccess import openOdb
import json

odb_path = __ODB_PATH__
info = {}
try:
    odb = openOdb(path=odb_path, readOnly=True)
    info['title'] = str(getattr(odb, 'title', ''))
    info['description'] = str(getattr(odb, 'description', ''))
    info['parts'] = list(odb.parts.keys()) if hasattr(odb, 'parts') else []
    info['instances'] = list(odb.rootAssembly.instances.keys()) if hasattr(odb, 'rootAssembly') else []
    steps = []
    for sname in odb.steps.keys():
        s = odb.steps[sname]
        frames = []
        for f in s.frames:
            frames.append({'frameId': f.frameId, 'frameValue': f.frameValue,
                           'description': str(getattr(f, 'description', ''))})
        step_info = {
            'name': sname,
            'procedure': str(getattr(s, 'procedure', '')),
            'totalTime': getattr(s, 'totalTime', 0.0),
            'frames': frames,
            'description': str(getattr(s, 'description', '')),
        }
        # field outputs available in first frame
        if s.frames:
            try:
                frame = s.frames[0]
                fov = []
                for desc in frame.fieldOutputs.keys():
                    fov.append(desc)
                step_info['fieldOutputs'] = fov
            except Exception:
                step_info['fieldOutputs'] = []
            try:
                frame = s.frames[-1]
                hov = []
                for desc in frame.historyOutputs.keys():
                    hov.append(desc)
                step_info['historyOutputs'] = hov
            except Exception:
                step_info['historyOutputs'] = []
        steps.append(step_info)
    info['steps'] = steps
    odb.close()
    result = {'success': True, 'data': info}
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
""".replace("__ODB_PATH__", json.dumps(odb_path))
    return await _exec(code, timeout or 60.0)


# ---------------------------------------------------------------------------
# Viewport capture
# ---------------------------------------------------------------------------


@mcp.tool()
async def capture_viewport(
    viewport_name: str = "",
    image_format: str = "PNG",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Capture a screenshot of an Abaqus viewport as a base64-encoded image.

    Leave viewport_name empty to use the current viewport.
    Supported formats: PNG, JPEG, TIFF, SVG.
    """
    code = r"""
import os, tempfile, base64
from abaqus import session

vp_name = __VP__
fmt = __FMT__

result = {}
try:
    if not vp_name or vp_name not in session.viewports.keys():
        vp_name = session.currentViewportName
    vp = session.viewports[vp_name]
    tmp = tempfile.NamedTemporaryFile(suffix='.' + fmt.lower(), delete=False)
    tmp.close()
    vp.view.print(filename=tmp.name, format=fmt.upper(), options='')
    with open(tmp.name, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    os.unlink(tmp.name)
    result = {
        'success': True,
        'viewport': vp_name,
        'format': fmt.lower(),
        'image_base64': b64,
        'size_bytes': len(b64) * 3 // 4,
    }
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
""".replace("__VP__", json.dumps(viewport_name)) \
      .replace("__FMT__", json.dumps(image_format.upper()))
    return await _exec(code, timeout or 60.0)


# ---------------------------------------------------------------------------
# MCP Resource - real-time status
# ---------------------------------------------------------------------------


@mcp.resource("abaqus://status")
def abaqus_status() -> str:
    """Current Abaqus MCP plugin status (running / stopped / ready)."""
    import json as _json
    try:
        r = _client(5.0).ping()
        if isinstance(r, dict) and r.get("ok", False):
            ret = r.get("return_value", r)
            return _json.dumps(ret, indent=2, ensure_ascii=False)
        return _json.dumps({"connected": False, "detail": str(r)}, indent=2)
    except Exception as e:
        return _json.dumps({"connected": False, "error": str(e)}, indent=2)


# ---------------------------------------------------------------------------
# MCP Resource - agent instructions
# ---------------------------------------------------------------------------


@mcp.resource("abaqus://agent-instructions")
def abaqus_agent_instructions() -> str:
    """Mandatory instructions for any AI agent controlling Abaqus via this MCP."""
    return INSTRUCTIONS


# ---------------------------------------------------------------------------
# MCP Prompts - guide LLM behaviour
# ---------------------------------------------------------------------------


@mcp.prompt()
def abaqus_scripting_strategy() -> str:
    """Best practices for writing Abaqus scripts that will be sent to an active
    Abaqus/CAE session via the `run_python` tool."""
    return r"""**Engineering AI SOP for Abaqus:**

1. **Check Working Directory First:** If building a new model from scratch, you MUST first ask the user whether they want to change the working directory. Use `set_workdir` if they confirm. Files (CAE, ODB, etc.) will be saved to the current working directory.
2. **No Blind Guessing:** If you are unsure of a method, attribute, or dictionary key in the Abaqus API, you MUST use `inspect` first.
3. **Step-by-Step Execution (Chunking):** Never write the entire script at once. Work in stages: (A) Geometry & Mesh -> (B) Materials & Sections -> (C) Assembly & Steps -> (D) Loads & BCs. After executing the code for one stage, STOP. Summarize what was created, and explicitly ask the user: "Should I proceed to the next stage?"
4. **UI Handoff for Complex Geometry:** Do NOT attempt to write complex `findAt` coordinate logic to select faces, edges, or vertices for Sets/Surfaces. It is highly error-prone，unless absolutely necessary. Instead, STOP execution and instruct the user: "Please manually create a Set/Surface for the required boundary condition in the Abaqus GUI. Let me know the exact name of the Set/Surface once you are done, and I will continue with the script."

## Error Recovery Standard Operating Procedure (SOP)
When `run_python` returns `"ok": False`, you MUST strictly follow this protocol:
1. **Read the Error:** Analyze the `core_error` and the `action_suggestion` in the JSON response.
2. **Execute the Suggestion:** Strictly follow the `action_suggestion`. If it mandates using `inspect`, you MUST call that tool immediately to inspect the parent object or dictionary. Use `depth=2` when you need to see nested structure. DO NOT guess or blind-retry without inspecting first.
3. **Web-Assisted Recovery:** If the `search_queries` field is present in the `recovery` metadata and inspection alone does not clearly resolve the error, use web search with those queries (include the Abaqus version) to find the correct API usage, method signatures, or naming conventions. Combine documentation findings with local inspection results.
4. **Silent Recovery:** DO NOT apologize to the user. DO NOT output conversational filler like "I'm sorry, let me fix that." Just silently trigger the tool call to gather the right info, rewrite the code based on the factual inspection, and execute again.
"""


@mcp.prompt()
def abaqus_workflow_create_and_run() -> str:
    """End-to-end workflow for creating a model, running an analysis, and post-processing results."""
    return r"""End-to-end Abaqus workflow via MCP:

1. **Check session**: `ping` - see existing models, check if clean.
2. **Set working directory (if needed)**: If building a new model from scratch, ask the user whether to change the working directory. Use `set_workdir(path="C:/your/project")` to set it. CAE/ODB files will be saved there.
3. **Create model**: Write Python code with `from abaqus import mdb, session` and `from abaqusConstants import *`. Create parts, materials, sections, assembly, steps, loads, BCs, mesh, and job.
4. **Submit job**: Use `run_python` — call `job.submit(consistencyChecking=False)` to launch asynchronously. Check status later with `mdb.jobs['YourJob'].status`.
5. **Inspect ODB**: Use `run_python` or `get_odb_info` to see available steps/frames/variables.
6. **Extract results**: Use `run_python` with `odbAccess` to extract field/history output.
7. **Capture viewport**: `capture_viewport()` to see visual results.

Always tell the user what you're doing at each step."""


@mcp.prompt()
def abaqus_odb_postprocessing() -> str:
    """Guide for extracting and visualizing results from Abaqus ODB files."""
    return r"""ODB post-processing via Abaqus MCP:

1. **Open and inspect**: `get_odb_info(odb_path)` to see steps, frames, instances, and available field/history variables.
2. **Field output**: Use `run_python` with `odbAccess.openOdb` and `frame.fieldOutputs[variable]`. Common variables:
   - `"S"` - Stress tensor components / von Mises
   - `"U"` - Displacement (U1, U2, U3, magnitude)
   - `"E"` - Strain tensor
   - `"RF"` - Reaction force
   - `"MISESMAX"` - Max von Mises (if defined)
3. **History output**: Use `run_python` with `step.historyRegions[name].historyOutputs[name].data` to extract time-history curves.
4. **Viewport**: Capture deformed shape / contour plots with `capture_viewport()` after setting the displayed object in Abaqus.
5. **Flexibility**: `run_python` gives you full control — filter by element set, section point, component, or any criteria the Abaqus API supports."""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
