# Abaqus Control MCP

[中文](README_ZH.md) | English

> Connect Claude, Cursor, and other MCP clients directly to your active Abaqus/CAE session.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

**Abaqus Control MCP** is a Model Context Protocol (MCP) bridge that lets you control a live Abaqus/CAE GUI session from Claude, Cursor, or any MCP-compatible AI client. Describe your analysis in natural language, and AI generates the Python code that runs instantly in the active Abaqus kernel—no background processes, no intermediate script files, no polling.

This is a **local, trusted automation tool** for engineers who want to integrate AI into their FEM workflow. The bridge listens on `127.0.0.1` by default, so all communication stays on your machine.

## Key Features

- 🎯 **Real-time GUI Control**: Directly manipulate the live Abaqus/CAE session—no noGUI process needed
- 💬 **Natural Language**: Describe your analysis goal to Claude, and it generates Python code for you
- 🔌 **Standard MCP Interface**: Works with Claude Desktop, Cursor, Codex, and any MCP client
- ⚡ **Zero File I/O**: Results return directly; no need to save/load intermediate files
- 🛡️ **Local-Only**: Listens on `127.0.0.1` by default—perfect for trusted workstations
- 📊 **Full Python Access**: Access the complete Abaqus Python 3.10 environment + `mdb` and `session` objects

## Architecture

```
MCP Client (Claude, Cursor, ...)
    |
    | stdio JSON-RPC
    v
uv run abaqus-control-mcp-server
    |
    | localhost TCP (127.0.0.1:48152)
    v
Abaqus/CAE GUI Plugin
    |
    | GUI main thread queue + abaqusGui.sendCommand(...)
    v
Abaqus/CAE Kernel Python 3.10
    |
    | mdb, session objects
    v
Live Model Tree & Results
```

The GUI plugin runs in the Abaqus GUI thread, preventing threading issues with `mdb` and `session`. Requests are queued and executed by the GUI main loop—safe and responsive.

## Quick Start

### Daily Workflow (one-time install, then just 2 steps)

Every time you use Abaqus Control MCP, you need **two components running simultaneously**:

> **Step A** (start plugin inside Abaqus/CAE) + **Step B** (start MCP Server in terminal)

<table>
<tr>
<th width="50%">Step A: Inside Abaqus/CAE</th>
<th width="50%">Step B: In your terminal</th>
</tr>
<tr>
<td>

```
Plug-ins -> Abaqus -> Start MCP GUI Agent
```

</td>
<td>

```bash
abaqus-control-mcp-server
```

</td>
</tr>
<tr>
<td>✅ Plugin starts in Abaqus GUI<br>
    TCP listening on 127.0.0.1:48152</td>
<td>✅ MCP Server starts stdio service<br>
    Waiting for MCP client connection</td>
</tr>
</table>

> **Once both are running**, your MCP client (Claude Code, Claude Desktop, Cursor, etc.) can connect and start controlling Abaqus with natural language.

### What You'll See

```
Terminal:  abaqus-control-mcp-server  ← keeps running
Abaqus:    Plug-ins → Abaqus → Start MCP GUI Agent  ← keeps running
Claude/Claude Code:    Describe your analysis task in natural language
            → generates Python code → sends to Abaqus → executes → returns result
                                                                      ↓
                                                    Model appears in your Abaqus/CAE in real-time
```

> ⚠️ **Important**: Start the Abaqus-side plugin (Step A) **before** starting the MCP Server (Step B). Reversing the order will cause a connection failure.

### Visual Flow

```
┌─────────────────────────────────────┐
│          Terminal (PC-side)          │
│  ┌─────────────────────────────┐    │
│  │ abaqus-control-mcp-server   │    │
│  └──────────┬──────────────────┘    │
│             │ MCP stdio protocol    │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │   MCP Client (Claude Code,   │    │
│  │   Claude Desktop, Cursor)    │    │
│  └─────────────────────────────┘    │
└────────────────┬────────────────────┘
                 │ TCP (127.0.0.1:48152)
                 ▼
┌─────────────────────────────────────┐
│         Abaqus/CAE (GUI-side)       │
│  ┌─────────────────────────────┐    │
│  │  Plug-ins → Abaqus → Start  │    │
│  │      MCP GUI Agent          │    │
│  └──────────┬──────────────────┘    │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │   Abaqus Kernel Python      │    │
│  │   (mdb, session objects)    │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

## Installation

### Prerequisites

- **Abaqus/CAE** (Windows)
- **Python 3.10+** (for the local environment, not Abaqus-side)

### Version Migration

**⚠️ Important: The GUI plugin is version-dependent.** If you upgrade or downgrade Abaqus, reinstall the plugin:

```bash
abaqus-control-install-plugin  # or re-run the PowerShell installer
```

The GUI plugin (`abaqus_mcp_gui_plugin.py`) directly imports `abaqusGui`, which changes between Abaqus versions.

Update these version-specific references:

- `README.md` and `README_ZH.md`: replace the example Abaqus executable path in the connectivity check with your installed version's path.
- Your local MCP client config or launch script, if you copied one and hardcoded an Abaqus executable path.
- Any custom shortcut or wrapper script that starts Abaqus/CAE and points at `ABQcaeK.exe`.

The core MCP server code under `src/abaqus_mcp_bridge/` does not change when switching Abaqus versions—only the installed plugin needs updating.

### Installation

#### 1. Install the MCP package

Use either `pip` or `uv`. The package install gives you the MCP server, the connectivity check, the plugin installer, and the support doctor command.

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

If you prefer `uv`:

```bash
uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

For local development, clone the repo and install it in editable mode:

```bash
git clone https://github.com/Whfkl/Abaqus-Control-MCP.git
cd Abaqus-Control-MCP
pip install -e .
```

#### 2. Install the Abaqus/CAE GUI plugin

The published package now includes a first-class installer:

```bash
abaqus-control-install-plugin
```

This installs the GUI plugin to `C:\Users\<YourUser>\abaqus_plugins\abaqus_mcp_gui_plugin.py` by default.
Set `ABAQUS_MCP_PLUGIN_DIR` or pass `--target-dir` if your Abaqus plugin search path is different.
After restart, Abaqus will show multiple MCP actions under the Abaqus-Control-MCP menu: start, status, open log, and stop.

If you cloned the repo and want to use the PowerShell helper instead, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_gui_plugin.ps1
```

#### 3. Restart Abaqus/CAE and verify connectivity

Restart Abaqus/CAE, then activate the plugin from:

```
Plug-ins -> Abaqus-Control-MCP -> Start MCP GUI Agent
```

Then verify the bridge:

```bash
abaqus-control-doctor --verify-connection
```

or, if you only want the connectivity check:

```bash
abaqus-control-check
```

Expected output (actual values will vary):

```
Abaqus MCP agent is reachable.
Ping:
{
  "python": "3.10.5 (main, Aug 12 2023) [MSC v.1934 64 bit (AMD64)]",
  "executable": "D:\\SIMULIA\\EstProducts\\2024\\win_b64\\code\\bin\\ABQcaeK.exe",
  "platform": "Windows-10-10.0.26200-SP0",
  "pid": 17644,
  "models": [
    "Model-1"
  ],
  "viewports": [
    "Viewport: 1"
  ],
  "guiProcess": {
    "python": "3.10.5",
    "platform": "Windows-10-10.0.26200-SP0",
    "thread": "MainThread"
  }
}
```

> If you see `Abaqus MCP agent is reachable.` with a `"thread": "MainThread"` entry, the connection is working.

## Usage

If you haven't installed yet, see [Installation](#installation) first.

Once installed, refer to the [Quick Start](#quick-start) above — the daily workflow is just **2 steps**.

### Configure your MCP Client

> **Make sure Abaqus/CAE is running** with the MCP GUI Agent plugin activated before connecting. The server connects to an existing Abaqus/CAE session.

#### Claude Code

Create or edit `.claude/mcp.json` in your project (or `~/.claude/mcp.json` for global use):

```json
{
  "mcpServers": {
    "abaqus": {
      "command": "abaqus-control-mcp-server",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "120"
      }
    }
  }
}
```

Claude Code will automatically start the server when needed. No manual terminal required — just make sure the Abaqus plugin is running first.

**Configure permissions (avoid prompts on every call)**

By default, Claude Code prompts for confirmation on every MCP tool call. You can whitelist read-only tools for auto-approval while keeping prompts for higher-risk operations. Edit `~/.claude/settings.json` or project-level `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__abaqus__abaqus_ping",
      "mcp__abaqus__abaqus_inspect_object",
      "mcp__abaqus__abaqus_get_model_info",
      "mcp__abaqus__abaqus_list_jobs",
      "mcp__abaqus__abaqus_get_odb_info",
      "mcp__abaqus__abaqus_get_field_output",
      "mcp__abaqus__abaqus_get_history_output"
    ]
  }
}
```

> The following tools are **not** auto-approved (still require manual confirmation):
> - `abaqus_execute_python` — can execute arbitrary code in Abaqus
> - `abaqus_submit_job` — submits and runs analysis jobs
> - `abaqus_get_viewport_image` — captures viewport screenshots
> - `abaqus_set_workdir` — changes the Abaqus working directory

> **Alternative with uv (no pip install)**: If you cloned the repo and use `uv`, set `"command": "uv"`, `"args": ["run", "abaqus-control-mcp-server"]`, and add `"cwd": "D:/path/to/Abaqus-Control-MCP"`.

#### Claude Desktop / Cursor

In your MCP client settings, add:

```json
{
  "mcpServers": {
    "abaqus": {
      "command": "abaqus-control-mcp-server",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "120"
      }
    }
  }
}
```

#### Environment Variables

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | Host address for the TCP bridge |
| `ABAQUS_MCP_PORT` | `48152` | Port for the TCP bridge |
| `ABAQUS_MCP_TIMEOUT` | `120` | Timeout in seconds for Python execution |

> **Windows path tip**: If using the `uv` + `cwd` approach, use forward slashes (`D:/path/to/...`) or escaped backslashes (`D:\\path\\to\\...`) — JSON does not allow unescaped backslashes.

### Example: Use Claude to Generate a Cantilever Beam

In Claude Code, Claude Desktop, or Cursor:

```
Me: Create a 1000mm x 100mm x 100mm steel cantilever beam model with 1000 elements.

Claude (using abaqus_execute_python): 
  I'll create a cantilever beam model with fixed left end and tip load.
  [generates Python code via abaqus_execute_python tool]

Result: Model appears in your active Abaqus/CAE window instantly.
```

### Python API

```python
from abaqus_mcp_bridge.client import AbaqusBridgeClient

client = AbaqusBridgeClient(timeout=60)

# Execute single-line expressions
result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
print(result)  # {'mode': 'eval', 'ok': True, 'return_value': [...], ...}

# Execute multi-line code with result variable
code = """
from abaqus import mdb
model = mdb.Model(name='Test')
result = {'model_name': model.name}
"""
result = client.execute(code)
print(result['return_value'])  # {'model_name': 'Test'}
```

## MCP Tools Available

| Tool | Description |
|------|-------------|
| `abaqus_ping` | Check connectivity + session state (models, viewports, PID) |
| `abaqus_execute_python` | Execute arbitrary Python code in the Abaqus kernel |
| `abaqus_get_model_info` | List parts, materials, steps, loads, BCs, interactions for all models |
| `abaqus_list_jobs` | List all analysis jobs with status, type, model association |
| `abaqus_submit_job` | Submit a job by name and wait for completion |
| `abaqus_get_odb_info` | Open ODB read-only: steps, frames, field/history output variables |
| `abaqus_get_field_output` | Extract field output data (S/E/U/RF) with min/max/mean stats |
| `abaqus_get_history_output` | Extract time-history curves from ODB history outputs |
| `abaqus_get_viewport_image` | Capture any viewport screenshot as base64 (PNG/JPEG/TIFF/SVG) |
| `abaqus_set_workdir` | Change the Abaqus working directory |

### `abaqus_ping`

Check if the Abaqus plugin is running and fetch current session state:
- Python version and executable path
- Current models and viewports
- GUI thread name (confirms main-thread execution)

### `abaqus_execute_python`

Execute Python code in the active Abaqus/CAE kernel:

- **Single-line expressions**: Uses `eval()`, returns the expression value
- **Multi-line code**: Uses `exec()`, returns the `result` variable if defined
- **Non-serializable objects**: Returns `repr()` and type name

Response includes `mode`, `ok`, `return_value`, `stdout`, `stderr`.

### `abaqus_get_model_info`

Returns structured info for every model in the session: part names, material names, step names, loads, boundary conditions, interactions, assembly instances, and viewport details.

### `abaqus_list_jobs`

Returns all `mdb.jobs` entries with status, type, model name, description, CPU/memory settings.

### `abaqus_submit_job`

Submit a job and block until completion. Default timeout is 600s. Returns final status and ODB path.

### `abaqus_get_odb_info`

Opens an ODB file in read-only mode and returns: title, description, part/instance names, step list with frame count/times, and available field/history output variable names.

### `abaqus_get_field_output`

Extract field output from an ODB. Parameters:
- `odb_path`, `step_name`, `frame_index`, `output_variable` (e.g. "S", "U", "E", "RF"), `instance_name`, `position`

Returns summary statistics (min/max/mean) and a sample of element/node values.

### `abaqus_get_history_output`

Extract time-history curves. If `history_output_name` is empty, lists all available history outputs per region. Otherwise returns `[(time, value), ...]` data points.

### `abaqus_get_viewport_image`

Capture a viewport screenshot as base64. Supported formats: `PNG`, `JPEG`, `TIFF`, `SVG`. Leave `viewport_name` empty for the current viewport.

### `abaqus_set_workdir`

Change the Abaqus working directory. Takes an absolute `path` and returns the previous and new working directory. Files (CAE, ODB, etc.) will be saved to the current working directory.

## MCP Resources

| URI | Description |
|-----|-------------|
| `abaqus://status` | Real-time plugin status (models, viewports, PID, platform) |

## MCP Prompts

| Prompt | Purpose |
|--------|---------|
| `abaqus_scripting_strategy` | Best practices for writing Abaqus Python code via MCP |
| `abaqus_workflow_create_and_run` | End-to-end workflow: create → submit → post-process |
| `abaqus_odb_postprocessing` | Guide for extracting and interpreting ODB results |

## FAQ

**Q: Is this production-safe?**

A: This is designed for **local, trusted automation on a single workstation**. The bridge listens on `127.0.0.1` only and executes Python with the same privileges as your Abaqus process. Do not expose the port to shared networks or the public internet.

**Q: Does this work with Abaqus Standard and Explicit?**

A: The GUI plugin works with any Abaqus/CAE GUI instance running on your machine. It doesn't matter whether you're analyzing with Standard or Explicit—the plugin bridges the GUI session.

**Q: What if I have multiple Abaqus windows open?**

A: The plugin bridges the **first** GUI instance that activates it. If you need to control a different session, restart that Abaqus window and activate the plugin again.

## Security & Privacy

- Listens on `127.0.0.1` by default—no public exposure.
- This is "remote code execution for Abaqus Python"—use only in trusted local environments.
- Logs are written to the system temp directory, not committed to the repository.
- If your scripts include local paths, usernames, or model names, these may appear in results or logs. Review examples before sharing.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `abaqus-control-install-plugin` not found | Reinstall the package in the same Python environment, then run `abaqus-control-doctor` to confirm the scripts are on PATH |
| `command not found: abaqus-control-mcp-server` | The package was installed into a different Python environment. Run `abaqus-control-doctor` or reinstall with the interpreter you use to launch the client |
| Plugin installation fails or is unclear | Run `abaqus-control-install-plugin --target-dir <path>` and inspect the JSON result; if needed, rerun with `--no-overwrite` or `-Force` in the PowerShell helper |
| No output from `abaqus-control-mcp-server` | **Normal** for stdio MCP Server — it doesn't print logs to stdout |
| `JSON parse error` when pressing Enter | Don't send empty lines to the stdio server |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | Use **Plug-ins -> Abaqus-Control-MCP -> Start MCP GUI Agent** menu, not File -> Run Script |
| Connection `timed out` | Check the plugin log at `$env:TEMP\abaqus_mcp_gui_plugin.log` |
| Model doesn't appear in GUI | Verify `abaqus-control-check` shows `"thread": "MainThread"` and a non-empty `models` list |
| Claude Code can't find the server | Make sure `abaqus-control-mcp-server` is in your PATH. Try `where abaqus-control-mcp-server` in terminal to verify. If using `uv`, add `"cwd"` to the MCP config pointing to the repo directory |

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit with clear messages
4. Open a pull request

Please ensure all changes are tested on a clean Abaqus installation.

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

**Made with ❤️ for Abaqus automation**

Questions? Suggestions? [Open an issue](https://github.com/Whfkl/Abaqus-Control-MCP/issues) or discuss on GitHub Discussions.
