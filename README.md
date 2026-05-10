# Abaqus Control MCP

[中文](README_ZH.md) | English

> Connect Claude, Cursor, and other MCP clients directly to your active Abaqus/CAE session.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Abaqus 2024](https://img.shields.io/badge/Abaqus-2024-brightgreen)](#)

**Abaqus Control MCP** is a Model Context Protocol (MCP) bridge that lets you control a live Abaqus/CAE GUI session from Claude, Cursor, or any MCP-compatible AI client. Describe your analysis in natural language, and AI generates the Python code that runs instantly in the active Abaqus kernel—no background processes, no intermediate script files, no polling.

This is a **local, trusted automation tool** for engineers who want to integrate AI into their FEM workflow. The bridge listens on `127.0.0.1` by default, so all communication stays on your machine.

## Key Features

- 🎯 **Real-time GUI Control**: Directly manipulate the live Abaqus/CAE session—no noGUI process needed
- 💬 **Natural Language**: Describe your analysis goal to Claude, and it generates Python code for you
- 🔌 **Standard MCP Interface**: Works with Claude Desktop, Cursor, Codex, and any MCP client
- ⚡ **Zero File I/O**: Results return directly; no need to save/load intermediate files
- 🛡️ **Local-Only**: Listens on `127.0.0.1` by default—perfect for trusted workstations
- 📊 **Full Python Access**: Access the complete Abaqus 2024 Python 3.10 environment + `mdb` and `session` objects

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

## Installation

### Prerequisites

- **Abaqus 2024** (Windows)
- **Python 3.10+** (for the local environment, not Abaqus-side)
- **uv** (Python package manager — [install guide](https://docs.astral.sh/uv/getting-started/installation/))

### Setup

1. **Clone the repository**

```bash
git clone https://github.com/Whfkl/Abaqus-Control-MCP.git
cd Abaqus-Control-MCP
```

2. **Install Python dependencies**

```bash
uv sync
```

> **Installation note**: If `uv sync` fails with a build error like `Expected a Python module at: src\abaqus_control_mcp\__init__.py`, make sure your `pyproject.toml` uses the `hatchling` build backend (not `uv_build`) with a proper `[tool.hatch.build.targets.wheel]` section pointing to the correct package directory. See the [pyproject.toml](pyproject.toml) in this repo for the correct configuration.

3. **Install the Abaqus/CAE GUI plugin**

Open **PowerShell** and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_gui_plugin.ps1
```

The plugin is installed to `C:\Users\<YourUser>\abaqus_plugins\abaqus_mcp_gui_plugin.py`.

4. **Restart Abaqus/CAE**, then activate the plugin via menu:

```
Plug-ins -> Abaqus -> Start MCP GUI Agent
```

5. **Verify connectivity**

```powershell
uv run abaqus-control-check
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

### Starting the MCP Server

> **Make sure Abaqus/CAE is running** with the MCP GUI Agent plugin activated before starting the MCP server. The server connects to an existing Abaqus/CAE session.

In your MCP client configuration (Claude Desktop, Cursor, etc.), add:

```json
{
  "mcpServers": {
    "abaqus": {
      "command": "uv",
      "args": ["run", "abaqus-control-mcp-server"],
      "cwd": "D:/path/to/Abaqus-Control-MCP",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "120"
      }
    }
  }
}
```

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | Host address for the TCP bridge |
| `ABAQUS_MCP_PORT` | `48152` | Port for the TCP bridge |
| `ABAQUS_MCP_TIMEOUT` | `120` | Timeout in seconds for Python execution |

> **Windows path tip**: Use forward slashes (`D:/path/to/...`) or escaped backslashes (`D:\\path\\to\\...`) in the `cwd` field — JSON does not allow unescaped backslashes.

### Example: Use Claude to Generate a Cantilever Beam

In Claude Desktop or Cursor:

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

### `abaqus_ping`

Check if the Abaqus plugin is running and fetch current session state:
- Python version and executable path
- Current models and viewports
- GUI thread name (confirms main-thread execution)

### `abaqus_execute_python`

Execute Python code in the active Abaqus/CAE kernel:

- **Single-line expressions**: Uses `eval()`, returns the expression value
- **Multi-line code**: Uses `exec()`, returns the `result` variable if defined
- **Return non-serializable objects**: Returns `repr()` and type name

Response includes:
- `mode`: `"eval"` or `"exec"`
- `ok`: `true` if successful
- `return_value`: The result
- `stdout`, `stderr`: Captured output

## Quick Demo

```powershell
# Create a demo cantilever beam model
uv run abaqus-control-demo
```

A 1000×100×100mm steel cantilever beam with 640 elements will appear in your active Abaqus/CAE Model Tree.

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
| `uv sync` fails: `Expected a Python module at: src\abaqus_control_mcp\__init__.py` | The `uv_build` backend incorrectly infers the package name from the project name. Use `hatchling` build backend instead — see [pyproject.toml](pyproject.toml) for the correct config |
| `uv sync` warns about `uv_build` not found | Install hatchling: `uv add --dev hatchling`, then update `pyproject.toml` to use `hatchling.build` |
| No output from `uv run abaqus-control-mcp-server` | **Normal** for stdio MCP Server — it doesn't print logs to stdout |
| `JSON parse error` when pressing Enter | Don't send empty lines to the stdio server |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | Use **Plug-ins -> Abaqus -> Start MCP GUI Agent** menu, not File -> Run Script |
| Connection `timed out` | Check the plugin log at `$env:TEMP\abaqus_mcp_gui_plugin.log` |
| Model doesn't appear in GUI | Verify `uv run abaqus-control-check` shows `"thread": "MainThread"` and a non-empty `models` list |
| `uv` command not found | Install uv from https://docs.astral.sh/uv/getting-started/installation/ |

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit with clear messages
4. Open a pull request

Please ensure all changes are tested on a clean Abaqus 2024 installation.

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

**Made with ❤️ for Abaqus automation**

Questions? Suggestions? [Open an issue](https://github.com/Whfkl/Abaqus-Control-MCP/issues) or discuss on GitHub Discussions.
