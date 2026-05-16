# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[中文](README_ZH.md) | English

> **Let AI drive Abaqus directly.** Describe the model you want — geometry, materials, loads, steps — and let the AI work inside your live Abaqus/CAE session.

**Abaqus Control MCP** connects Claude, Cursor, and any other MCP-compatible client to a running Abaqus/CAE instance. You describe the task, the AI translates it into Abaqus actions, and the model updates in real time.

> **Older Abaqus versions** ship Python 2. If your Abaqus uses Python 2, use the [Python 2 compatible fork](https://github.com/hp283260133-bit/Abaqus-Control-MCP-abaqus2021) instead.

### Why this?

- **Work directly in the live GUI** — actions run in your active Abaqus window, so geometry, mesh, and results stay visible as they change.
- **Full access to Abaqus objects** — `mdb`, `session`, `odb`, and the rest of the Python API are directly available, letting AI do the work.
- **Keep the session interactive** — engineers can inspect progress at any time without stopping the session.
- **Stay local** — the bridge listens on `127.0.0.1:48152`, so nothing leaves your machine.
- **Use any MCP client** — Claude Code, Claude Desktop, Cursor, and other compatible clients can connect with the same setup.


## Setup

**AI agent one-click install**

If your AI agent supports natural-language installation, just prompt it with:

```text
install https://github.com/Whfkl/Abaqus-Control-MCP
```

**1. Install the package**

`uv` (recommended):

```bash
uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

Or `pip`:

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

Dependencies are declared in `pyproject.toml` — no `requirements.txt` needed. Both methods install four CLI commands (`abaqus-control-mcp-server`, `abaqus-control-check`, `abaqus-control-doctor`, `abaqus-control-setup`).

**2. Install the GUI plugin**

```bash
abaqus-control-setup
```

This copies `gui_plugin.py` to `~/abaqus_plugins/`. Set `ABAQUS_MCP_PLUGIN_DIR` to override.

**3. Start Abaqus/CAE, activate the plugin**

```
Plug-ins → Abaqus-Control-MCP → Start MCP Bridge
```

**4. Configure your MCP client**

`abaqus-control-setup` automatically registers the MCP server with Claude Code (runs `claude mcp add` under the hood). If you skipped that or need to re-register:

```bash
# Global (all projects)
claude mcp add -s user -e ABAQUS_MCP_HOST=127.0.0.1 \
  -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 \
  abaqus /absolute/path/to/abaqus-control-mcp-server

# Current project only
claude mcp add -s local -e ABAQUS_MCP_HOST=127.0.0.1 \
  -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 \
  abaqus /absolute/path/to/abaqus-control-mcp-server
```

> Use the absolute path to the executable — Claude Code's subprocess may not have your shell PATH. Run `which abaqus-control-mcp-server` (or `where` on Windows) to find it.

Claude Code starts the MCP server automatically when you open a session — no need to start it manually.

To reduce permission prompts, whitelist read-only tools in `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__abaqus__ping",
      "mcp__abaqus__inspect",
      "mcp__abaqus__list_jobs",
      "mcp__abaqus__get_odb_info"
    ]
  }
}
```

For **Cursor** or other MCP clients, add the server config to their respective settings files. The MCP server uses standard stdio transport.

**5. Verify**

```bash
abaqus-control-check
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `ping` | Check connectivity + session state (models, viewports, PID) |
| `run_python` | Execute arbitrary Python code in the Abaqus kernel |
| `inspect` | Inspect an object path — returns keys or public attributes |
| `list_jobs` | List all jobs with status, type, model |
| `get_odb_info` | Open ODB read-only: steps, frames, available variables |
| `capture_viewport` | Capture viewport screenshot as base64 (PNG/JPEG/TIFF/SVG) |
| `set_workdir` | Change the Abaqus working directory |

> Model creation, job submission, field/history output extraction — all go through `run_python`. This gives you full Abaqus API access without parameter limitations.

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
| Claude Code doesn't see MCP tools | 1. Run `claude mcp list` to check if `abaqus` is registered. 2. If not listed, run `claude mcp add -s user -e ABAQUS_MCP_HOST=127.0.0.1 -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 abaqus /absolute/path/to/abaqus-control-mcp-server`. 3. Restart Claude Code after any config change. |

## Security

Listens on `127.0.0.1` only. Executes Python with the same privileges as your Abaqus process. Logs are written to system temp. Review output for local paths or model names before sharing.

## License

MIT — see [LICENSE](LICENSE).
