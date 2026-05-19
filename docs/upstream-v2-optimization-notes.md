# Optimization Notes On Top Of The New Upstream Structure

This branch is based on the upstream refactor that moved the package from
`src/abaqus_mcp_bridge` to `abaqus_mcp_bridge`, added `abaqus-control-setup`,
auto-installs the GUI plugin from the MCP server, and renamed core tools to
shorter names such as `run_python`, `inspect`, and `capture_viewport`.

The upstream direction is good. The remaining gap is compatibility with
Abaqus/CAE 2021 and other releases that still run Python 2.7 inside the Abaqus
GUI/kernel process.

## What This Branch Optimizes

### 1. Abaqus 2021 Python 2.7 GUI Plugin Compatibility

The upstream GUI plugin still imports and uses Python 3-only names directly:

```python
import queue
import socketserver
contextlib.redirect_stdout
contextlib.redirect_stderr
ast.Constant
ast.unparse
os.cpu_count
```

This branch keeps the upstream behavior but adds Python 2.7 fallbacks for:

- `Queue` / `SocketServer`
- `TimeoutError`
- `basestring`
- socket send/receive string handling
- stdout/stderr redirection in the generated kernel wrapper
- AST key literal parsing
- safe `exec` of compiled code
- `multiprocessing.cpu_count()` fallback

### 2. Non-ASCII Windows Path Stability

On Windows, Abaqus 2021 often returns filesystem paths, tracebacks, and exception
strings as local-codepage byte strings. If the user profile contains non-ASCII
characters, direct UTF-8 decoding may fail.

This branch adds normalization before:

- base64 encoding submitted code and response paths;
- JSON response serialization;
- socket responses from the GUI agent.

This prevents half-written response JSON files and timeout symptoms caused by
encoding failures.

### 3. Safer JSON Response Writing

The generated kernel wrapper now recursively converts dictionaries, lists,
tuples, sets, byte strings, repr strings, and error metadata into JSON-safe text
before calling `json.dump(..., ensure_ascii=True)`.

The goal is not to hide errors. The goal is to make every error return as a
complete MCP response instead of leaving a truncated JSON file behind.

### 4. Duplicate GUI Menu Protection

If the plugin is loaded both by Abaqus plugin scanning and by a startup
environment hook, duplicate menu items can appear. This branch guards menu
registration with:

```python
_ABAQUS_CONTROL_MCP_MENU_REGISTERED
```

### 5. Job Submission Compatibility

The upstream tool now asks for explicit CPU/GPU choices, which is a good safety
improvement. This branch adjusts the generated Abaqus-side job submission code
to set CPU/GPU values through `job.setValues(...)` before `job.submit(...)`,
which is more compatible with Abaqus job APIs than passing resource options
directly to `submit`.

## Suggested Upstream Direction

1. Keep the new simplified package structure and setup CLI.
2. Officially support two Abaqus GUI runtime tiers:
   - Abaqus Python 2.7, for Abaqus 2021 and older.
   - Abaqus Python 3, for newer Abaqus releases.
3. Add a tiny compatibility module or inline helper block for the GUI plugin.
4. Add a self-test path that runs under Abaqus Python:

```powershell
abaqus python -m py_compile "%USERPROFILE%\abaqus_plugins\abaqus_mcp_gui_plugin.py"
```

5. Add a runtime smoke test:

```text
ping -> run_python("result = {'ok': True}") -> run_python(raise non-ASCII exception)
```

6. Add a README compatibility note for non-ASCII Windows usernames and local
codepage handling.

## Validation Target

The expected validation environment for this branch is:

- Windows
- Abaqus/CAE 2021
- Abaqus Python 2.7.15
- user profile path containing non-ASCII characters
- MCP bridge running on `127.0.0.1:48152`

In the original test environment, these compatibility fixes allowed the bridge
to create, solve, post-process, and report a three-story steel frame implicit
dynamic transient analysis.
