# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[中文](README_ZH.md) | English

> **Chat with your Abaqus.** Describe the FEM analysis you need — geometry, materials, loads — and AI executes it directly in your live Abaqus/CAE session. No scripting, no file juggling, no `noGUI` processes.

**Abaqus Control MCP** connects Claude, Cursor, and other MCP-compatible AI tools to a running Abaqus/CAE instance. You talk to the AI. The AI talks to Abaqus. Your model updates in real time.

### Why this?

- **Live GUI feedback** — code runs in your active Abaqus window. Every part, step, and mesh change appears as it happens.
- **No intermediate files** — results stream back through the TCP bridge. No `.py` scripts littering your working directory.
- **Full API access** — `mdb`, `session`, and every Abaqus Python module are available. No sandbox, no restrictions.
- **Local-only** — the bridge listens on `127.0.0.1:48152`. Nothing leaves your workstation.
- **Standard MCP** — works with Claude Code, Claude Desktop, Cursor, and any MCP-compatible client. Drop in the config and go.


## Setup

**1. Install the package**

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

Dependencies are declared in `pyproject.toml` — no `requirements.txt` needed. `uv` users can clone the repo and run directly:

```bash
git clone https://github.com/Whfkl/Abaqus-Control-MCP.git
cd Abaqus-Control-MCP
uv run abaqus-control-mcp-server
```

**2. Install the GUI plugin**

```bash
abaqus-control-setup
```

This copies `gui_plugin.py` to `~/abaqus_plugins/`. Set `ABAQUS_MCP_PLUGIN_DIR` to override.

**3. Start Abaqus/CAE, activate the plugin**

```
Plug-ins → Abaqus-Control-MCP → Start MCP Bridge
```

**4. Start the MCP server**

```bash
abaqus-control-mcp-server
```

**5. Configure your MCP client**

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

To reduce permission prompts, whitelist read-only tools in `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__abaqus__ping",
      "mcp__abaqus__inspect",
      "mcp__abaqus__get_model_info",
      "mcp__abaqus__list_jobs",
      "mcp__abaqus__get_odb_info",
      "mcp__abaqus__get_field_output",
      "mcp__abaqus__get_history_output"
    ]
  }
}
```

**6. Verify**

```bash
abaqus-control-check
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `ping` | Check connectivity + session state (models, viewports, PID) |
| `run_python` | Execute arbitrary Python code in the Abaqus kernel |
| `inspect` | Inspect an object path — returns keys or public attributes |
| `get_model_info` | List parts, materials, steps, loads, BCs, interactions |
| `list_jobs` | List all jobs with status, type, model |
| `submit_job` | Submit a job by name and wait for completion |
| `get_odb_info` | Open ODB read-only: steps, frames, available variables |
| `get_field_output` | Extract field output (S/E/U/RF) with min/max/mean |
| `get_history_output` | Extract time-history curves from ODB history outputs |
| `capture_viewport` | Capture viewport screenshot as base64 (PNG/JPEG/TIFF/SVG) |
| `set_workdir` | Change the Abaqus working directory |

## MCP Prompts

| Prompt | Purpose |
|--------|---------|
| `abaqus_scripting_strategy` | Best practices for Abaqus scripting via MCP + error recovery SOP |
| `abaqus_workflow_create_and_run` | End-to-end: create model → submit job → post-process |
| `abaqus_odb_postprocessing` | Guide for extracting and interpreting ODB results |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP bridge host |
| `ABAQUS_MCP_PORT` | `48152` | TCP bridge port |
| `ABAQUS_MCP_TIMEOUT` | `120` | Execution timeout in seconds |
| `ABAQUS_MCP_PLUGIN_DIR` | `~/abaqus_plugins` | GUI plugin target directory |

## Python API

```python
from abaqus_mcp_bridge.client import AbaqusBridgeClient

client = AbaqusBridgeClient(timeout=60)
result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
print(result['return_value'])  # ['Model-1', ...]
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `command not found: abaqus-control-mcp-server` | Reinstall or run `abaqus-control-doctor` |
| No output from server | Normal for stdio MCP server — it doesn't print to stdout |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | Use **Plug-ins** menu, not File → Run Script |
| Connection timed out | Start the Abaqus plugin **before** the MCP server |
| Model doesn't appear in GUI | Run `abaqus-control-check` — verify `"thread": "MainThread"` |

## Security

Listens on `127.0.0.1` only. Executes Python with the same privileges as your Abaqus process. Logs are written to system temp. Review output for local paths or model names before sharing.

## License

MIT — see [LICENSE](LICENSE).
