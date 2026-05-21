"""MCP stdio server that forwards Python execution requests to Abaqus.

Core tools: ping, run_python — plus viewport capture and ODB metadata.
Most debugging should come from run_python's structured error payload.
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

INSTRUCTIONS = """You are an elite simulation engineer controlling a live Abaqus/CAE session via MCP tools.
Your goal is to build robust, highly stable, and production-grade finite element models.

CORE SIMULATION RULES:
1. SEMANTIC GEOMETRY (Golden Rule): Better not use raw coordinates or `findAt()` to assign boundary conditions, sections, or loads.
    - Immediately after creating a part or feature, grab its geometry using robust methods:
      * `getByBoundingBox(xMin, yMin, zMin, xMax, yMax, zMax)`
      * `getByBoundingCylinder(...)`
      * Topological filtering (e.g., `part.faces[0:1]`, `part.edges.findAt(...)` only for static boundaries).
    - Wrap the grabbed geometry into named Sets (for cells/nodes/vertices) or Surfaces (for faces/edges) IMMEDIATELY.
    - All subsequent steps (meshing, section assignments, interactions, loads, and BCs) MUST reference these semantic names (e.g., `region=part.sets['Set-Name']` or `surface=instance.surfaces['Surf-Name']`).

2. DYNAMIC CHUNKING: Do not write massive scripts that perform modeling, meshing, solver submission, and post-processing all at once.
    - Divide your work into logical validation milestones (e.g., Phase 1: Base Geometry & Named Sets -> Phase 2: Assembly, Step & Mesh -> Phase 3: Physics, Loads & Submission).
    - Verify each phase's correctness via execution before proceeding. No rigid linear chains — adapt the phase size to the task's complexity.

3. DOCKING & DIAGNOSTICS (No Guessing & Web Search): Never guess Abaqus API methods, attributes, or signatures.
    - If live local reflection is insufficient, or if you encounter complex API signature mismatches, ALWAYS call the web search tool (including the term 'Abaqus' and target versions, e.g., 'Abaqus 2024 Python API ...') to find official documentation, forum examples, or method signatures.


4. WORKING DIRECTORY & PERSISTENCE: Every Abaqus analysis generates a massive number of solver files (.inp, .odb, .sta, .msg, etc.).
    - Before writing any model, ALWAYS query or set a clean working directory (using the `set_workdir` tool or standard Python `os.chdir` at the start of your script). Do NOT let Abaqus run in default system paths, which causes permission errors and directory pollution.
    - Periodically save the database (.cae file) to the working directory using `mdb.saveAs(pathName=...)` (e.g., `mdb.saveAs(pathName='D:/temp/My-Model.cae')`). Never leave the CAE session unsaved, ensuring persistence against solver crashes.

5. CONCISE PAIR-PROGRAMMING: Avoid robotic headers, repetitive intent declarations, and verbose apologies. Keep explanations technical, clear, and direct. Focus on finite element modeling best practices.

"""

mcp = FastMCP("abaqus-control-mcp", instructions=INSTRUCTIONS)


def _client(timeout: float | None = None) -> AbaqusBridgeClient:
    return AbaqusBridgeClient(
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        timeout=timeout if timeout is not None else DEFAULT_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Generic python execution wrapper
# ---------------------------------------------------------------------------


async def _exec(code: str, timeout: float | None = None) -> dict[str, Any]:
    """Execute Python code in Abaqus and return the result dict."""
    return await anyio.to_thread.run_sync(_client(timeout).execute, code)


def _format_error_to_markdown(result: dict[str, Any]) -> str:
    """Render a crash payload into a compact, highly readable Markdown diagnostic panel."""
    parts: list[str] = []

    error_type = result.get("error_type", "Unknown")
    short_type = error_type.rsplit(".", 1)[-1] if "." in error_type else error_type
    core_error = result.get("core_error", "Unknown error")
    error_line = result.get("error_line")

    # Extract message from core_error to avoid prefix duplication
    prefix = f"{short_type}:"
    if core_error.startswith(prefix):
        msg = core_error[len(prefix):].strip()
    else:
        msg = core_error

    location = f" at line {error_line}" if error_line else ""
    parts.append(f"{short_type}{location}: {msg}")

    # Indented recovery details
    recovery = result.get("recovery") or {}
    if recovery:
        # KeyError details
        if "missing_key" in recovery:
            if recovery.get("parent_object_path"):
                parts.append(f"  Container: {recovery['parent_object_path']}")
            if "available_keys_sample" in recovery:
                sample = recovery["available_keys_sample"]
                if isinstance(sample, list):
                    if len(sample) > 20:
                        sample = sample[:20] + ["..."]
                    parts.append(f"  Available: {sample}")
            if recovery.get("possible_keys"):
                parts.append(f"  Similar: {recovery['possible_keys']}")

        # AttributeError details
        elif "missing_attribute" in recovery:
            parts.append(f"  Missing Attribute: {recovery['missing_attribute']}")
            if recovery.get("object_type"):
                parts.append(f"  Object Type: {recovery['object_type']}")
            if recovery.get("parent_object_path"):
                parts.append(f"  Object Path: {recovery['parent_object_path']}")
            if recovery.get("possible_members"):
                parts.append(f"  Similar: {recovery['possible_members']}")

        # NameError details
        elif "missing_variable" in recovery:
            parts.append(f"  Undefined Variable: {recovery['missing_variable']}")
            if recovery.get("import_suggestion"):
                parts.append(f"  Import Suggestion: {recovery['import_suggestion']}")

        # SyntaxError details
        elif "syntax_line" in recovery:
            if recovery.get("syntax_offset"):
                parts.append(f"  Syntax Error offset: {recovery['syntax_offset']}")
            if recovery.get("syntax_text"):
                parts.append(f"  Problem text: {recovery['syntax_text'].strip()}")

        # TypeError or fallback callable details
        elif "callable_signature" in recovery or "call_target" in recovery:
            if recovery.get("call_target"):
                parts.append(f"  Call Target: {recovery['call_target']}")
            if recovery.get("callable_signature"):
                parts.append(f"  Expected Signature: {recovery['callable_signature']}")
            if recovery.get("callable_summary"):
                parts.append(f"  Description: {recovery['callable_summary']}")
            if recovery.get("possible_keywords"):
                parts.append(f"  Similar Keywords: {recovery['possible_keywords']}")

    # Failed code line
    code_excerpt = result.get("code_excerpt")
    if code_excerpt:
        failed_line = None
        for line in code_excerpt.splitlines():
            if line.startswith(">>"):
                parts_line = line.split("|", 1)
                if len(parts_line) == 2:
                    failed_line = parts_line[1].strip()
                break
        if failed_line:
            parts.append(f"  Code: {failed_line}")

    # stdout/stderr summary & content
    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()
    if stdout:
        lines_count = len(stdout.splitlines())
        if lines_count <= 3:
            parts.append(f"  stdout: {stdout}")
        else:
            parts.append(f"  stdout: (captured, {lines_count} lines)")
    if stderr:
        lines_count = len(stderr.splitlines())
        if lines_count <= 3:
            parts.append(f"  stderr: {stderr}")
        else:
            parts.append(f"  stderr: (captured, {lines_count} lines)")

    return "\n".join(parts)


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
    Stdout, stderr, traceback, error line, and code excerpts are included in the response.
    """
    if not code.strip():
        raise ValueError("code must not be empty")
    result = await _exec(code, timeout)
    if not result.get("ok", False):
        raise RuntimeError(_format_error_to_markdown(result))
    return result


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
async def monitor_job_status(job_name: str = "", timeout: float | None = None) -> dict[str, Any]:
    """Monitor Abaqus job status and optional OS-level progress from .sta/.msg files.

    Args:
        job_name: If provided, read [JobName].sta and [JobName].msg in the working
            directory to extract recent progress and diagnostics. If empty, list
            all jobs defined in the current Abaqus session.
    """
    code = r"""
import os
import re
from abaqus import mdb

job_name = __JOB_NAME__

def _tail_lines(path, count):
    try:
        with open(path, 'r') as f:
            lines = f.read().splitlines()
        if count <= 0:
            return []
        return lines[-count:]
    except Exception:
        return []

def _grep_tail(path, patterns, limit):
    try:
        rx = re.compile('|'.join(patterns))
        matches = []
        with open(path, 'r') as f:
            for line in f:
                if rx.search(line):
                    matches.append(line.rstrip())
        return matches[-limit:] if limit > 0 else matches
    except Exception:
        return []

result = {}
if not job_name:
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
else:
    sta_path = os.path.join(os.getcwd(), job_name + '.sta')
    msg_path = os.path.join(os.getcwd(), job_name + '.msg')
    progress_lines = _tail_lines(sta_path, 5)
    diagnostic_lines = _grep_tail(msg_path, [r'^\*\*\*ERROR', r'^\*\*\*WARNING'], 10)
    result = {
        'job_name': job_name,
        'sta_path': sta_path,
        'msg_path': msg_path,
        'progress_tail': progress_lines,
        'diagnostics_tail': diagnostic_lines,
    }
""".replace("__JOB_NAME__", json.dumps(job_name.strip()))
    return await _exec(code, timeout)


@mcp.tool()
async def inspect_odb(odb_path: str, timeout: float | None = None) -> dict[str, Any]:
    """Open an ODB file (read-only) and return its metadata.

    Returns steps (with sliced frames and total time), parts, instances, section points,
    and available field/history output variables with positions and components.
    """
    code = r"""
from abaqus import mdb
from odbAccess import openOdb

odb_path = __ODB_PATH__
info = {}
odb = None
try:
    odb = openOdb(path=odb_path, readOnly=True)
    info['title'] = str(getattr(odb, 'title', ''))
    info['description'] = str(getattr(odb, 'description', ''))
    info['parts'] = list(odb.parts.keys()) if hasattr(odb, 'parts') else []
    info['instances'] = list(odb.rootAssembly.instances.keys()) if hasattr(odb, 'rootAssembly') else []
    steps = []

    def _slice_frames(frames):
        count = len(frames)
        if count <= 5:
            return list(frames)
        idxs = [0]
        for k in range(1, 4):
            idxs.append(int(round(k * (count - 1) / 4.0)))
        idxs.append(count - 1)
        seen = set()
        uniq = []
        for i in idxs:
            if i not in seen and 0 <= i < count:
                uniq.append(i)
                seen.add(i)
        return [frames[i] for i in uniq]

    def _field_meta(field_output):
        meta = {}
        try:
            meta['position'] = str(getattr(field_output, 'position', ''))
        except Exception:
            meta['position'] = ''
        comps = []
        try:
            comps = list(getattr(field_output, 'componentLabels', []) or [])
        except Exception:
            comps = []
        try:
            invariants = list(getattr(field_output, 'validInvariants', []) or [])
        except Exception:
            invariants = []
        meta['components'] = comps + [str(x) for x in invariants if str(x) not in comps]
        return meta

    for sname in odb.steps.keys():
        s = odb.steps[sname]
        frames = []
        for f in _slice_frames(s.frames):
            frames.append({
                'frameId': f.frameId,
                'frameValue': f.frameValue,
                'description': str(getattr(f, 'description', '')),
            })
        step_info = {
            'name': sname,
            'procedure': str(getattr(s, 'procedure', '')),
            'totalTime': getattr(s, 'totalTime', 0.0),
            'frames': frames,
            'description': str(getattr(s, 'description', '')),
        }
        if s.frames:
            try:
                frame = s.frames[0]
                fov = []
                for desc in frame.fieldOutputs.keys():
                    fo = frame.fieldOutputs[desc]
                    meta = _field_meta(fo)
                    meta['name'] = desc
                    fov.append(meta)
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
    result = {'success': True, 'data': info}
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
finally:
    try:
        if odb is not None:
            odb.close()
    except Exception:
        pass
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


@mcp.resource("abaqus://session-telemetry")
def session_telemetry() -> str:
    """Retrieve active Abaqus/CAE session telemetry and environment metadata."""
    import json as _json
    try:
        r = _client(5.0).ping()
        if isinstance(r, dict):
            return _json.dumps(r, indent=2, ensure_ascii=False)
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





def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
