"""MCP stdio server that forwards Python execution requests to Abaqus.

Provides high-level tools for model inspection, job management, ODB post-processing,
and viewport capture - all implemented as Python code templates executed via the
generic `run_python` tool. No changes to the socket protocol are needed.
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


DEFAULT_HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))

INSTRUCTIONS = """You are controlling a live Abaqus/CAE session via MCP tools.

MANDATORY RULES:
1. INTENT DECLARATION: Before every run_python call, output a sentence: "I will now [action] to [purpose]."
2. CHUNKING: Never write the full script at once. Execute in stages: (A) Geometry & Mesh → (B) Materials & Sections → (C) Assembly & Steps → (D) Loads & BCs. Pause after each, summarize, and ask the user: "Should I proceed to the next stage?"
3. NO GUESSING: If unsure about any Abaqus API method, attribute, or key — call inspect first. Never guess.
4. UI HANDOFF: Do NOT write complex findAt coordinate logic for selecting faces/edges/vertices. Stop and ask the user to create the Set/Surface in the Abaqus GUI, then continue with the exact name.
5. ERROR RECOVERY: When run_python returns "ok": False, read core_error and action_suggestion, call inspect if suggested, rewrite based on facts — no apology, no filler.
6. WORKING DIRECTORY: Before building a new model, ask the user if they want to change the working directory.
7. JOB SUBMISSION: Before calling submit_job, call ping to get cpu_count. Tell the user how many cores are available and ask how many they want to use — do NOT assume all cores. Also ask about num_gpus. Do not submit without num_cpus set.
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


def _inspect_code(object_path: str) -> str:
    """Build Abaqus-side code for introspecting an object path."""
    return r"""
from abaqus import mdb, session

object_path = __OBJECT_PATH__

def _jsonable_key(key):
    try:
        import json
        json.dumps(key, ensure_ascii=False)
        return key
    except Exception:
        return repr(key)

try:
    obj = eval(object_path, {"__builtins__": {}}, {"mdb": mdb, "session": session})
    keys_method = getattr(obj, "keys", None)
    if callable(keys_method):
        result = {
            "ok": True,
            "object_path": object_path,
            "kind": "mapping",
            "type": type(obj).__name__,
            "keys": [_jsonable_key(key) for key in keys_method()],
        }
    else:
        result = {
            "ok": True,
            "object_path": object_path,
            "kind": "object",
            "type": type(obj).__name__,
            "attributes": [name for name in dir(obj) if not name.startswith("_")],
        }
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
""".replace("__OBJECT_PATH__", json.dumps(object_path))


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
async def inspect(object_path: str, timeout: float | None = None) -> dict[str, Any]:
    """Inspect an Abaqus object path and return available keys or public attributes.

    Examples:
        - ``mdb.models['Model-1'].parts``
        - ``session.viewports``
        - ``mdb.models['Model-1'].rootAssembly``
    """
    if not object_path.strip():
        raise ValueError("object_path must not be empty")
    return await _exec(_inspect_code(object_path.strip()), timeout)


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


# ---------------------------------------------------------------------------
# Advanced query tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_model_info(timeout: float | None = None) -> dict[str, Any]:
    """Get detailed information about all models in the current Abaqus session.

    Returns parts, materials, steps, loads, BCs, interactions, and assembly instances
    for each model, plus current viewport info.
    """
    code = r"""
from abaqus import mdb, session
info = {'models': [], 'viewports': []}
for model_name in mdb.models.keys():
    model = mdb.models[model_name]
    m = {'name': model_name, 'parts': list(model.parts.keys()),
         'materials': list(model.materials.keys()),
         'steps': list(model.steps.keys()),
         'loads': list(model.loads.keys()) if hasattr(model, 'loads') else [],
         'bcs': list(model.boundaryConditions.keys()) if hasattr(model, 'boundaryConditions') else [],
         'interactions': list(model.interactions.keys()) if hasattr(model, 'interactions') else []}
    if hasattr(model, 'rootAssembly') and model.rootAssembly is not None:
        if hasattr(model.rootAssembly, 'instances'):
            m['assembly'] = list(model.rootAssembly.instances.keys())
    info['models'].append(m)
if hasattr(session, 'viewports'):
    info['viewports'] = list(session.viewports.keys())
if hasattr(session, 'currentViewportName'):
    info['currentViewport'] = session.currentViewportName
info['workingDirectory'] = __import__('os').getcwd()
result = info
"""
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
async def submit_job(job_name: str, num_cpus: int | None = None, num_gpus: int = 0, timeout: float | None = None) -> dict[str, Any]:
    """Submit an Abaqus analysis job by name and wait for completion.

    The job must already be defined in `mdb.jobs`. Default timeout is 600 s.

    Args:
        job_name: Name of a job already defined in mdb.jobs.
        num_cpus: Number of CPUs. Leave unset or call ping first to detect.
        num_gpus: Number of GPUs (default 0).
    """
    cpus_val = num_cpus if num_cpus is not None else -1
    code = r"""
from abaqus import mdb
job_name = __JOB_NAME__
if job_name not in mdb.jobs:
    result = {'success': False, 'error': 'Job "%s" not found' % job_name}
else:
    job = mdb.jobs[job_name]
    kwargs = {'consistencyChecking': False}
    nc = __NUM_CPUS__
    if nc > 0:
        kwargs['numCpus'] = nc
    ng = __NUM_GPUS__
    if ng > 0:
        kwargs['numGpus'] = ng
    job.submit(**kwargs)
    job.waitForCompletion()
    status = str(getattr(job, 'status', 'UNKNOWN'))
    result = {
        'success': True,
        'job': job_name,
        'status': status,
        'model': str(getattr(mdb.jobs[job_name], 'model', '')),
    }
    try:
        result['odb'] = str(job.name) + '.odb'
    except Exception:
        pass
""".replace("__JOB_NAME__", json.dumps(job_name)) \
   .replace("__NUM_CPUS__", str(cpus_val)) \
   .replace("__NUM_GPUS__", str(num_gpus))
    return await _exec(code, timeout or 600.0)


# ---------------------------------------------------------------------------
# ODB post-processing tools
# ---------------------------------------------------------------------------


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


@mcp.tool()
async def get_field_output(
    odb_path: str,
    step_name: str = "",
    frame_index: int = -1,
    output_variable: str = "S",
    instance_name: str = "",
    position: str = "INTEGRATION_POINT",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Extract field output data from an ODB file.

    Args:
        odb_path: Full path to the .odb file.
        step_name: Step name (empty = last step).
        frame_index: Frame index (-1 = last frame).
        output_variable: Field output variable name, e.g. "S" (stress), "E" (strain),
            "U" (displacement), "RF" (reaction force), "MISESMAX" etc.
        instance_name: Instance name (empty = first instance).
        position: Output position - "INTEGRATION_POINT", "NODAL", "ELEMENT_NODAL", etc.
    Returns summary statistics (min, max, mean) and a sample of values.
    """
    code = r"""
from odbAccess import openOdb

odb_path = __ODB_PATH__
step_name = __STEP_NAME__
frame_index = __FRAME_INDEX__
output_var = __OV__
inst_name = __INST_NAME__
pos_name = __POS__

result = {}
try:
    odb = openOdb(path=odb_path, readOnly=True)
    # Determine step
    if not step_name or step_name not in odb.steps.keys():
        step_name = list(odb.steps.keys())[-1]
    step = odb.steps[step_name]
    # Determine frame
    if frame_index < 0 or frame_index >= len(step.frames):
        frame_index = len(step.frames) - 1
    frame = step.frames[frame_index]
    # Get field output
    fo = frame.fieldOutputs[output_var]
    # Filter by instance if needed
    if inst_name:
        values = [v for v in fo.values if v.instance.name == inst_name]
    else:
        values = list(fo.values)
    # Compute stats
    magnitudes = []
    sample = []
    for v in values:
        try:
            mag = (v.magnitude if hasattr(v, 'magnitude') and v.magnitude is not None
                   else float(v.data))
            magnitudes.append(mag)
            if len(sample) < 10:
                el_label = getattr(v, 'elementLabel', getattr(v, 'nodeLabel', 0))
                sample.append({'label': el_label, 'magnitude': round(mag, 4),
                               'data': str(v.data)[:80]})
        except Exception:
            pass
    import statistics
    result = {
        'success': True,
        'step': step_name,
        'frame': frame_index,
        'frameValue': frame.frameValue,
        'variable': output_var,
        'position': str(getattr(fo, 'position', '')),
        'numValues': len(values),
        'min': round(min(magnitudes), 4) if magnitudes else None,
        'max': round(max(magnitudes), 4) if magnitudes else None,
        'mean': round(statistics.mean(magnitudes), 4) if magnitudes else None,
        'sample': sample,
    }
    odb.close()
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
""".replace("__ODB_PATH__", json.dumps(odb_path)) \
      .replace("__STEP_NAME__", json.dumps(step_name)) \
      .replace("__FRAME_INDEX__", str(int(frame_index))) \
      .replace("__OV__", json.dumps(output_variable)) \
      .replace("__INST_NAME__", json.dumps(instance_name)) \
      .replace("__POS__", json.dumps(position))
    return await _exec(code, timeout or 60.0)


@mcp.tool()
async def get_history_output(
    odb_path: str,
    step_name: str = "",
    history_output_name: str = "",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Extract history output data from an ODB file.

    Useful for time-history curves (displacement, stress at specific points,
    reaction forces, energy, etc.). If history_output_name is empty, lists all
    available history outputs.
    """
    code = r"""
from odbAccess import openOdb

odb_path = __ODB_PATH__
step_name = __STEP__
ho_name = __HO__

result = {}
try:
    odb = openOdb(path=odb_path, readOnly=True)
    if not step_name or step_name not in odb.steps.keys():
        step_name = list(odb.steps.keys())[-1]
    step = odb.steps[step_name]

    if not ho_name:
        # List all available history outputs
        regions = {}
        for hk in step.historyRegions.keys():
            region = step.historyRegions[hk]
            outputs = list(region.historyOutputs.keys())
            regions[hk] = outputs
        result = {'success': True, 'step': step_name, 'historyRegions': regions}
    else:
        # Extract data for specific history output
        data = []
        for hk in step.historyRegions.keys():
            region = step.historyRegions[hk]
            if ho_name in region.historyOutputs:
                ho = region.historyOutputs[ho_name]
                for point_data in ho.data:  # list of tuples (time, value)
                    data.append({'time': round(point_data[0], 6), 'value': round(point_data[1], 6)})
        magnitudes = [d['value'] for d in data] if data else []
        result = {
            'success': True,
            'step': step_name,
            'historyOutput': ho_name,
            'numPoints': len(data),
            'min': round(min(magnitudes), 4) if magnitudes else None,
            'max': round(max(magnitudes), 4) if magnitudes else None,
            'data': data[:1000],  # limit to first 1000 points
        }
    odb.close()
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
""".replace("__ODB_PATH__", json.dumps(odb_path)) \
      .replace("__STEP__", json.dumps(step_name)) \
      .replace("__HO__", json.dumps(history_output_name))
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
2. **Execute the Suggestion:** Strictly follow the `action_suggestion`. If it mandates using `inspect`, you MUST call that tool immediately to inspect the parent object or dictionary. DO NOT guess or blind-retry without inspecting first.
3. **Silent Recovery:** DO NOT apologize to the user. DO NOT output conversational filler like "I'm sorry, let me fix that." Just silently trigger the tool call to gather the right info, rewrite the code based on the factual inspection, and execute again.
"""


@mcp.prompt()
def abaqus_workflow_create_and_run() -> str:
    """End-to-end workflow for creating a model, running an analysis, and post-processing results."""
    return r"""End-to-end Abaqus workflow via MCP:

1. **Check session**: `ping` - see existing models, check if clean.
2. **Set working directory (if needed)**: If building a new model from scratch, ask the user whether to change the working directory. Use `set_workdir(path="C:/your/project")` to set it. CAE/ODB files will be saved there.
3. **Create model**: Write Python code with `from abaqus import mdb, session` and `from abaqusConstants import *`. Create parts, materials, sections, assembly, steps, loads, BCs, mesh, and job.
4. **Submit job**: `submit_job(job_name="YourJob")` - waits for completion.
5. **Inspect ODB**: `get_odb_info(odb_path="path/to/YourJob.odb")` to see available steps/frames/variables.
6. **Extract results**: `get_field_output(odb_path="...", output_variable="S")` for stress, `"U"` for displacement, etc.
7. **Capture viewport**: `capture_viewport()` to see visual results.

Always tell the user what you're doing at each step."""


@mcp.prompt()
def abaqus_odb_postprocessing() -> str:
    """Guide for extracting and visualizing results from Abaqus ODB files."""
    return r"""ODB post-processing via Abaqus MCP:

1. **Open and inspect**: `get_odb_info(odb_path)` to see steps, frames, instances, and available field/history variables.
2. **Field output**: Use `get_field_output(odb_path, step_name, frame_index, output_variable)`. Common variables:
   - `"S"` - Stress tensor components / von Mises
   - `"U"` - Displacement (U1, U2, U3, magnitude)
   - `"E"` - Strain tensor
   - `"RF"` - Reaction force
   - `"MISESMAX"` - Max von Mises (if defined)
3. **History output**: Use `get_history_output(odb_path, step_name)` first to list available outputs, then call with a specific `history_output_name` to get time-history data.
4. **Viewport**: Capture deformed shape / contour plots with `capture_viewport()` after setting the displayed object in Abaqus.
5. **Limitations**: The bridge returns summary statistics (min/max/mean) and samples - not full datasets. For detailed analysis, use Abaqus/Viewer locally."""


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
