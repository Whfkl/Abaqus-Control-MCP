"""MCP server for a running Abaqus/CAE session."""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from .client import AbaqusBridgeClient, BridgeError


mcp = MCPServer(
    "abaqus-control-mcp",
    version="2.0.0",
    instructions="Control the active Abaqus/CAE session through six local tools. Check connection with ping; use executionId to correlate each result. A timed-out running execution has an unknown outcome and must not be retried blindly.",
)


def _bridge() -> AbaqusBridgeClient:
    return AbaqusBridgeClient(
        host=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("ABAQUS_MCP_PORT", "48152")),
        timeout=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "120")),
    )


def _result(data: dict[str, Any], *, error: bool = False, image_data: str | None = None) -> CallToolResult:
    content = [TextContent(text=json.dumps(data, ensure_ascii=False, default=str))]
    if image_data is not None:
        content.append(ImageContent(data=image_data, mimeType="image/png"))
    return CallToolResult(
        content=content,
        structuredContent=data,
        isError=error,
    )


def _bridge_error(exc: Exception) -> dict[str, Any]:
    data: dict[str, Any] = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
    if isinstance(exc, BridgeError):
        data["executionId"] = exc.execution_id
        data["state"] = exc.state
        data["error"]["type"] = exc.error_type
    return data


def _validation_error(message: str) -> CallToolResult:
    return _result({"ok": False, "executionId": str(uuid.uuid4()), "error": {"type": "ValueError", "message": message}}, error=True)


def _python_error(execution: dict[str, Any]) -> dict[str, Any]:
    error_type = execution.get("error_type", "ExecutionError").rsplit(".", 1)[-1]
    error: dict[str, Any] = {
        "type": error_type,
        "message": execution.get("message") or execution.get("core_error", "Abaqus execution failed"),
    }
    primary = execution.get("primary_frame") or {}
    code_line = execution.get("code_line")
    if code_line is None:
        excerpt = execution.get("code_excerpt") or ""
        marked = next((line for line in excerpt.splitlines() if line.startswith(">>")), "")
        code_line = marked.split("|", 1)[-1].strip() if marked else None
    location = {"file": primary.get("file"), "line": primary.get("line") or execution.get("error_line"),
                "function": primary.get("function"), "code": code_line}
    location = {key: value for key, value in location.items() if value is not None}
    if location:
        error["at"] = location

    recovery = execution.get("recovery") or {}
    kept = ("missing_key", "possible_keys", "available_key_count", "available_keys_sample",
            "missing_attribute", "object_type", "possible_members", "missing_variable",
            "possible_names", "import_suggestion", "call_target", "callable_signature",
            "possible_keywords", "syntax_offset")
    suggestions = {key: recovery[key] for key in kept
                   if key in recovery and recovery[key] is not None and recovery[key] != []}
    if suggestions:
        error["suggestions"] = suggestions

    user_frames = [frame for frame in execution.get("frames", [])
                   if frame.get("file", "").startswith("<abaqus-mcp:")
                   or frame.get("file") == primary.get("file")]
    if user_frames and primary and user_frames[-1] == primary:
        user_frames.pop()
    if user_frames:
        error["callers"] = user_frames[-3:]
    return error


async def _execute(code: str) -> dict[str, Any]:
    return await anyio.to_thread.run_sync(_bridge().execute, code)


def _execution_result(execution: dict[str, Any]) -> CallToolResult:
    data: dict[str, Any] = {
        "executionId": execution.get("executionId") or execution.get("requestId"),
        "ok": bool(execution.get("ok")),
    }
    if data["ok"]:
        data["value"] = execution.get("return_value")
    else:
        data["error"] = _python_error(execution)
    for stream in ("stdout", "stderr"):
        if execution.get(stream):
            data[stream] = execution[stream]
    return _result(data, error=not data["ok"])


def _operation_result(execution: dict[str, Any]) -> CallToolResult:
    if not execution.get("ok"):
        return _execution_result(execution)
    value = execution.get("return_value")
    if not isinstance(value, dict):
        return _result({"ok": False, "executionId": execution.get("executionId"), "error": {"type": "ProtocolError", "message": "Abaqus operation did not return an object"}}, error=True)
    data = {"ok": True, "executionId": execution.get("executionId") or execution.get("requestId"), **value}
    if execution.get("stdout"):
        data["stdout"] = execution["stdout"]
    if execution.get("stderr"):
        data["stderr"] = execution["stderr"]
    return _result(data)


def _code(template: str, **values: Any) -> str:
    for key, value in values.items():
        template = template.replace("__" + key.upper() + "__", repr(value))
    return template


@mcp.tool(
    description="Check the active Abaqus/CAE connection and return its session details.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def ping() -> CallToolResult:
    try:
        session = await anyio.to_thread.run_sync(_bridge().ping)
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)
    return _result({"ok": True, "executionId": session.get("executionId") or session.get("requestId"), "session": session})


@mcp.tool(
    description="Run Python in the active Abaqus/CAE kernel. Expressions return their value; statements may assign result."
)
async def run_python(code: str) -> CallToolResult:
    if not code.strip():
        return _validation_error("code must not be empty")
    try:
        execution = await _execute(code)
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)

    return _execution_result(execution)


@mcp.tool(description="Set the active Abaqus/CAE working directory and return the previous and current paths.")
async def set_workdir(path: str) -> CallToolResult:
    if not path.strip():
        return _validation_error("path must not be empty")
    code = _code("""
import os
target = __PATH__
if not os.path.isabs(target):
    raise ValueError('path must be absolute')
if not os.path.isdir(target):
    raise FileNotFoundError(target)
previous = os.getcwd()
os.chdir(target)
result = {'previous': previous, 'current': os.getcwd()}
""", path=path.strip())
    try:
        return _operation_result(await _execute(code))
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)


_JOB_CODE = r"""
import os, re, time
from abaqus import mdb

name = __JOB_NAME__
terminate = __TERMINATE__
since = __SINCE__
root = os.getcwd()

def _tail(path, maximum=262144):
    if not os.path.isfile(path):
        return ''
    with open(path, 'rb') as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(0, handle.tell() - maximum))
        return handle.read().decode('utf-8', 'replace')

def _file_info(path):
    return {'path': path, 'exists': os.path.isfile(path), 'modifiedAt': os.path.getmtime(path) if os.path.isfile(path) else None}

def _status(job):
    try:
        return str(job.status).upper() if job is not None else None
    except Exception:
        return None

if not name:
    result = {'jobs': [{'name': key, 'caeStatus': _status(mdb.jobs[key])} for key in mdb.jobs.keys()], 'workingDirectory': root}
else:
    if name != os.path.basename(name) or name in ('.', '..'):
        raise ValueError('job_name must be a single file name')
    job = mdb.jobs[name] if name in mdb.jobs else None
    if terminate and job is None:
        raise ValueError('Termination requires a job registered in the current CAE session')
    kill_requested = False
    kill_error = None
    if terminate:
        if _status(job) in ('COMPLETED', 'ABORTED', 'TERMINATED', 'CHECK_COMPLETED'):
            kill_error = 'Job already has a terminal CAE status; no kill command sent'
        else:
            try:
                job.kill()
                kill_requested = True
            except Exception as exc:
                kill_error = '%s: %s' % (type(exc).__name__, exc)
            deadline = time.time() + 5.0
            while kill_requested and time.time() < deadline and _status(job) not in ('TERMINATED', 'ABORTED', 'COMPLETED'):
                time.sleep(0.25)
    paths = {ext: os.path.join(root, name + '.' + ext) for ext in ('log', 'sta', 'dat', 'msg', 'lck')}
    files = {ext: _file_info(path) for ext, path in paths.items()}
    log = _tail(paths['log'])
    sta = _tail(paths['sta'])
    dat = _tail(paths['dat'])
    msg = _tail(paths['msg'])
    cae = _status(job)
    combined = '\n'.join((log, sta, dat, msg))
    diagnostics = [line.strip() for line in combined.splitlines() if re.search(r'^\s*(?:\*{2,}\s*|ABAQUS\s+)(?:ERROR|WARNING)\b', line, re.I)]
    errors = [line for line in diagnostics if re.search(r'\bERROR\b', line, re.I)][-10:]
    warnings = [line for line in diagnostics if re.search(r'\bWARNING\b', line, re.I)][-10:]
    log_upper = log.upper()
    sta_upper = sta.upper()
    file_state = None
    if re.search(r'ABAQUS JOB .* (?:ABORTED|FAILED)|THE ANALYSIS HAS NOT BEEN COMPLETED|\bA N A L Y S I S\s+T E R M I N A T E D\b', log_upper):
        file_state = 'FAILED'
    elif re.search(r'ABAQUS JOB .* TERMINATED|USER REQUESTED TERMINATION', log_upper):
        file_state = 'TERMINATED'
    elif re.search(r'ABAQUS JOB .* COMPLETED|THE ANALYSIS HAS COMPLETED SUCCESSFULLY', log_upper + '\n' + sta_upper):
        file_state = 'COMPLETED'
    cae_state = {'COMPLETED': 'COMPLETED', 'CHECK_COMPLETED': 'COMPLETED', 'ABORTED': 'FAILED', 'TERMINATED': 'TERMINATED', 'RUNNING': 'RUNNING', 'CHECK_RUNNING': 'RUNNING', 'SUBMITTED': 'SUBMITTED'}.get(cae)
    lock_exists = files['lck']['exists']
    terminal_mtime = max([files[ext]['modifiedAt'] for ext in ('log', 'sta') if files[ext]['modifiedAt'] is not None] or [0])
    file_is_fresh = since is not None and terminal_mtime >= since
    effective_file_state = file_state if since is None or file_is_fresh else None
    conflict = bool(effective_file_state and cae_state and ((cae_state in ('RUNNING', 'SUBMITTED')) or (cae_state in ('COMPLETED', 'FAILED', 'TERMINATED') and cae_state != effective_file_state)))
    if conflict:
        state, source = 'UNKNOWN', 'conflicting CAE and file evidence'
    elif cae_state in ('COMPLETED', 'FAILED', 'TERMINATED') and lock_exists:
        state, source = 'UNKNOWN', 'terminal CAE status while lock file exists'
    elif cae_state in ('COMPLETED', 'FAILED', 'TERMINATED'):
        state, source = cae_state, 'CAE job status'
    elif effective_file_state and not lock_exists and job is None and file_is_fresh:
        state, source = effective_file_state, 'log/status file modified after since'
    elif file_state and not lock_exists and job is None:
        state, source = 'UNKNOWN', 'file terminal marker but current run freshness unverified'
    elif file_state and not lock_exists and job is not None and cae_state is None:
        state, source = 'UNKNOWN', 'terminal file marker without a current CAE run'
    elif effective_file_state and lock_exists:
        state, source = 'UNKNOWN', 'terminal file marker while lock file exists'
    elif cae_state:
        state, source = cae_state, 'CAE job status'
    elif lock_exists:
        state, source = 'UNKNOWN', 'lock file only; process not verified'
    else:
        state, source = 'UNKNOWN', 'insufficient evidence'
    progress = [line.strip() for line in sta.splitlines() if line.strip()]
    numeric = [line for line in progress if re.match(r'^\d+\s+\d+\s+', line)]
    current_step = None
    increment = None
    if numeric:
        match = re.match(r'^(\d+)\s+(\d+)\b', numeric[-1])
        current_step, increment = int(match.group(1)), int(match.group(2))
    result = {
        'jobName': name, 'workingDirectory': root, 'state': state,
        'terminal': state in ('COMPLETED', 'FAILED', 'TERMINATED'),
        'source': source, 'caeStatus': cae, 'fileState': file_state,
        'currentStep': current_step, 'increment': increment,
        'progressTail': progress[-8:], 'errors': errors, 'warnings': warnings,
        'errorCountInTails': len([line for line in diagnostics if re.search(r'\bERROR\b', line, re.I)]),
        'warningCountInTails': len([line for line in diagnostics if re.search(r'\bWARNING\b', line, re.I)]),
        'files': files, 'observedAt': time.time(), 'since': since,
        'runFreshness': 'confirmed by CAE' if source == 'CAE job status' and state in ('COMPLETED', 'FAILED', 'TERMINATED') else ('bounded by since' if file_is_fresh else 'unverified'),
    }
    if terminate:
        result['termination'] = {'requested': kill_requested, 'confirmed': state == 'TERMINATED' and not lock_exists, 'error': kill_error}
"""


@mcp.tool(description="Read Abaqus job progress, terminal state and diagnostics. Use since (Unix seconds) to bind file-only evidence to a run; terminate requests kill with confirmation.")
async def monitor_job_status(job_name: str = "", terminate: bool = False, since: float | None = None) -> CallToolResult:
    if terminate and not job_name.strip():
        return _validation_error("job_name is required for termination")
    if since is not None and (not 0 <= since <= 4102444800):
        return _validation_error("since must be a Unix timestamp between 1970 and 2100")
    code = _code(_JOB_CODE, job_name=job_name.strip(), terminate=terminate, since=since)
    try:
        return _operation_result(await _execute(code))
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)


_ODB_CODE = r"""
import math, os
from odbAccess import openOdb

path = os.path.abspath(__ODB_PATH__)
step_name = __STEP__
frame_index = __FRAME__
variable = __VARIABLE__
set_name = __SET_NAME__
component = __COMPONENT__
history_region = __HISTORY_REGION__
history_variable = __HISTORY_VARIABLE__
max_points = __MAX_POINTS__

if not os.path.isfile(path):
    raise FileNotFoundError(path)
odb = openOdb(path=path, readOnly=True)
try:
    def _step_meta(name, step):
        domain = str(getattr(step, 'domain', ''))
        start = float(getattr(step, 'totalTime', 0.0)) if domain == 'TIME' else None
        duration = float(getattr(step, 'timePeriod', 0.0)) if domain == 'TIME' else None
        count = len(step.frames)
        indices = list(range(count)) if count <= 5 else sorted(set([0, count // 4, count // 2, (3 * count) // 4, count - 1]))
        frames = [{'index': i, 'frameId': step.frames[i].frameId,
                   'frameValue': step.frames[i].frameValue,
                   'description': str(getattr(step.frames[i], 'description', ''))}
                  for i in indices]
        fields = {}
        if count:
            for frame in (step.frames[0], step.frames[-1]):
                for key in frame.fieldOutputs.keys():
                    field = frame.fieldOutputs[key]
                    fields[key] = {'name': key, 'type': str(getattr(field, 'type', '')),
                                   'components': list(getattr(field, 'componentLabels', ()) or ())}
        regions = []
        for key in list(step.historyRegions.keys())[:100]:
            region = step.historyRegions[key]
            regions.append({'name': key, 'variables': list(region.historyOutputs.keys())[:100]})
        return {'name': name, 'description': str(getattr(step, 'description', '')),
                'procedure': str(getattr(step, 'procedure', '')), 'domain': domain,
                'startTime': start, 'endTime': start + duration if start is not None and duration is not None else None,
                'duration': duration, 'frameCount': count, 'frames': frames,
                'fieldOutputs': list(fields.values()), 'historyRegions': regions}

    names = list(odb.steps.keys())
    if step_name and step_name not in odb.steps:
        raise KeyError('Unknown step %r; available: %s' % (step_name, names))
    selected_name = step_name or (names[-1] if names else None)
    info = {'path': path, 'title': str(getattr(odb, 'title', '')),
            'description': str(getattr(odb, 'description', '')),
            'parts': list(odb.parts.keys()), 'instances': list(odb.rootAssembly.instances.keys()),
            'assemblyNodeSets': list(odb.rootAssembly.nodeSets.keys())[:200],
            'assemblyElementSets': list(odb.rootAssembly.elementSets.keys())[:200],
            'instanceSets': {key: {'nodeSets': list(odb.rootAssembly.instances[key].nodeSets.keys())[:100],
                                   'elementSets': list(odb.rootAssembly.instances[key].elementSets.keys())[:100]}
                             for key in list(odb.rootAssembly.instances.keys())[:100]},
            'steps': [_step_meta(name, odb.steps[name]) for name in names]}
    if variable or history_variable:
        if selected_name is None:
            raise ValueError('ODB has no steps')
        step = odb.steps[selected_name]
        info['selectedStep'] = selected_name
    if variable:
        if not step.frames:
            raise ValueError('Selected step has no frames')
        index = frame_index if frame_index >= 0 else len(step.frames) + frame_index
        if not 0 <= index < len(step.frames):
            raise IndexError('frame index out of range; frameCount=%d' % len(step.frames))
        frame = step.frames[index]
        if variable not in frame.fieldOutputs:
            raise KeyError('Field %r unavailable in selected frame; available: %s' % (variable, list(frame.fieldOutputs.keys())))
        field = frame.fieldOutputs[variable]
        if set_name:
            matches = []
            assembly = odb.rootAssembly
            location = str(field.values[0].position) if field.values else ''
            collection_names = ('nodeSets',) if location == 'NODAL' else ('elementSets',)
            for collection_name in collection_names:
                collection = getattr(assembly, collection_name)
                if set_name in collection:
                    matches.append(collection[set_name])
            for instance_name in assembly.instances.keys():
                instance = assembly.instances[instance_name]
                for collection_name in collection_names:
                    collection = getattr(instance, collection_name)
                    for key in collection.keys():
                        if set_name == instance_name + '.' + key:
                            matches.append(collection[key])
            if not matches:
                raise KeyError('Unknown set %r; use assembly set or INSTANCE.SET' % set_name)
            if len(matches) != 1:
                raise ValueError('Set name is ambiguous; use INSTANCE.SET or a unique assembly set')
            field = field.getSubset(region=matches[0])
        if component:
            if component not in field.componentLabels:
                raise KeyError('Unknown component %r; available: %s' % (component, list(field.componentLabels)))
            field = field.getScalarField(componentLabel=component)
        count = 0
        minimum = None
        maximum = None
        for item in field.values:
            data = item.data
            if hasattr(data, '__len__') and not isinstance(data, (str, bytes)):
                if component:
                    raise ValueError('Component extraction returned nonscalar data')
                if str(getattr(field, 'type', '')) not in ('VECTOR', 'SCALAR'):
                    raise ValueError('Tensor field requires a component')
                scalar = math.sqrt(sum(float(part) ** 2 for part in data))
            else:
                scalar = float(data)
            if not math.isfinite(scalar):
                continue
            count += 1
            minimum = scalar if minimum is None else min(minimum, scalar)
            maximum = scalar if maximum is None else max(maximum, scalar)
        info['fieldSummary'] = {'step': selected_name, 'frameIndex': index,
                                'frameValue': frame.frameValue, 'variable': variable,
                                'component': component, 'set': set_name,
                                'quantity': 'component' if component else ('magnitude' if str(getattr(field, 'type', '')) == 'VECTOR' else 'scalar'),
                                'count': count, 'min': minimum, 'max': maximum}
    if history_variable:
        keys = list(step.historyRegions.keys())
        region_key = history_region or (keys[0] if len(keys) == 1 else None)
        if region_key is None:
            raise ValueError('Specify history_region; available: %s' % keys[:100])
        if region_key not in step.historyRegions:
            raise KeyError('Unknown history region %r; available: %s' % (region_key, keys[:100]))
        outputs = step.historyRegions[region_key].historyOutputs
        if history_variable not in outputs:
            raise KeyError('Unknown history variable %r; available: %s' % (history_variable, list(outputs.keys())))
        points = outputs[history_variable].data
        count = len(points)
        indices = list(range(count)) if count <= max_points else sorted(set([round(i * (count - 1) / float(max_points - 1)) for i in range(max_points)]))
        sampled = [[float(points[i][0]), float(points[i][1])] for i in indices]
        values = [float(pair[1]) for pair in points if math.isfinite(float(pair[1]))]
        info['historySummary'] = {'step': selected_name, 'region': region_key, 'variable': history_variable,
                                  'pointCount': count, 'returnedPoints': len(sampled),
                                  'min': min(values) if values else None, 'max': max(values) if values else None,
                                  'points': sampled, 'xAxis': 'step time' if str(getattr(step, 'domain', '')) == 'TIME' else str(getattr(step, 'domain', ''))}
    result = info
finally:
    odb.close()
"""


@mcp.tool(description="Inspect an ODB read-only. Optionally summarize one field at step/frame/set, or a history curve by region and variable.", annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
async def inspect_odb(odb_path: str, step: str = "", frame: int = -1, variable: str = "", set_name: str = "", component: str = "", history_region: str = "", history_variable: str = "", max_points: int = 200) -> CallToolResult:
    if not odb_path.strip():
        return _validation_error("odb_path must not be empty")
    if not 2 <= max_points <= 1000:
        return _validation_error("max_points must be between 2 and 1000")
    code = _code(_ODB_CODE, odb_path=odb_path, step=step, frame=frame, variable=variable, set_name=set_name, component=component, history_region=history_region, history_variable=history_variable, max_points=max_points)
    try:
        return _operation_result(await _execute(code))
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)


_CAPTURE_CODE = r"""
import base64, os, struct, tempfile
from abaqus import session
import abaqusConstants

viewport_name = __VIEWPORT_NAME__
image_format = __IMAGE_FORMAT__
save_path = __SAVE_PATH__
formats = {'PNG': abaqusConstants.PNG, 'TIFF': abaqusConstants.TIFF,
           'SVG': abaqusConstants.SVG, 'EPS': abaqusConstants.EPS, 'PS': abaqusConstants.PS}
if viewport_name:
    if viewport_name not in session.viewports:
        raise KeyError('Unknown viewport %r; available: %s' % (viewport_name, list(session.viewports.keys())))
else:
    viewport_name = session.currentViewportName
if image_format not in formats:
    raise ValueError('Unsupported image format: %s' % image_format)
if image_format in ('SVG', 'EPS', 'PS') and not save_path:
    raise ValueError('SVG/EPS/PS requires save_path')
if save_path:
    save_path = os.path.abspath(save_path)
    if not os.path.isdir(os.path.dirname(save_path)):
        raise FileNotFoundError(os.path.dirname(save_path))
    if not save_path.lower().endswith('.' + image_format.lower()):
        raise ValueError('save_path extension must match image_format')
fd, base = tempfile.mkstemp(prefix='abaqus_mcp_capture_')
os.close(fd)
os.unlink(base)
source = None
destination_temp = None
try:
    session.printToFile(fileName=base, format=formats[image_format],
                        canvasObjects=(session.viewports[viewport_name],))
    for candidate in (base + '.' + image_format.lower(), base + '.' + image_format.upper(), base):
        if os.path.isfile(candidate) and os.path.getsize(candidate):
            source = candidate
            break
    if source is None:
        raise RuntimeError('Abaqus printToFile did not produce the requested image')
    with open(source, 'rb') as handle:
        raw = handle.read()
    width = height = None
    if image_format == 'PNG' and raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) >= 24:
        width, height = struct.unpack('>II', raw[16:24])
    if save_path:
        output_fd, destination_temp = tempfile.mkstemp(prefix='.abaqus_mcp_', dir=os.path.dirname(save_path))
        with os.fdopen(output_fd, 'wb') as output:
            output.write(raw)
        os.replace(destination_temp, save_path)
        destination_temp = None
    result = {'viewport': viewport_name, 'format': image_format.lower(),
              'savedPath': save_path, 'sizeBytes': len(raw),
              'width': width, 'height': height,
              'imageBase64': base64.b64encode(raw).decode('ascii') if image_format in ('PNG', 'TIFF') and len(raw) <= 10 * 1024 * 1024 else None}
    if result['imageBase64'] is None and not save_path:
        raise ValueError('Image exceeds 10 MiB; provide save_path')
finally:
    for candidate in (destination_temp, source, base, base + '.' + image_format.lower(), base + '.' + image_format.upper()):
        if candidate and os.path.isfile(candidate):
            try:
                os.unlink(candidate)
            except OSError:
                pass
"""


@mcp.tool(description="Capture a CAE viewport. PNG/TIFF return a native MCP image; optionally save the file. SVG/EPS/PS require save_path.")
async def capture_viewport(viewport_name: str = "", image_format: str = "PNG", save_path: str = "") -> CallToolResult:
    image_format = image_format.upper()
    if image_format not in ("PNG", "TIFF", "SVG", "EPS", "PS"):
        return _validation_error("image_format must be PNG, TIFF, SVG, EPS or PS")
    code = _code(_CAPTURE_CODE, viewport_name=viewport_name, image_format=image_format, save_path=save_path)
    try:
        execution = await _execute(code)
    except Exception as exc:
        return _result(_bridge_error(exc), error=True)
    if not execution.get("ok"):
        return _execution_result(execution)
    value = execution.get("return_value")
    if not isinstance(value, dict):
        return _result({"ok": False, "executionId": execution.get("executionId"), "error": {"type": "ProtocolError", "message": "capture returned an invalid value"}}, error=True)
    value = dict(value)
    encoded_image = value.pop("imageBase64", None)
    data = {"ok": True, "executionId": execution.get("executionId") or execution.get("requestId"), **value}
    if encoded_image is not None:
        try:
            base64.b64decode(encoded_image, validate=True)
        except ValueError as exc:
            return _result({"ok": False, "executionId": data["executionId"], "error": {"type": "ProtocolError", "message": str(exc)}}, error=True)
    if encoded_image is not None and image_format == "TIFF":
        return CallToolResult(content=[TextContent(text=json.dumps(data, ensure_ascii=False)), ImageContent(data=encoded_image, mimeType="image/tiff")], structuredContent=data)
    return _result(data, image_data=encoded_image)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
