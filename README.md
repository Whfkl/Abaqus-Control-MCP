# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[中文](README_ZH.md) | English

> **Let AI drive Abaqus directly.** Describe the model you want — geometry, materials, loads, steps — and let the AI work inside your live Abaqus/CAE session.

**Abaqus Control MCP** connects Claude Code, Codex, Antigravity, and any other MCP-compatible client to a running Abaqus/CAE instance. You describe the task, the AI translates it into Abaqus actions, and the model updates in real time.

> **Older Abaqus versions** ship Python 2. If your Abaqus uses Python 2, use the [Python 2 compatible fork](https://github.com/hp283260133-bit/Abaqus-Control-MCP-abaqus2021) instead.

### Why this?

- **Work directly in the live GUI** — actions run in your active Abaqus window, so geometry, mesh, and results stay visible as they change.
- **Full access to Abaqus objects** — `mdb`, `session`, `odb`, and the rest of the Python API are directly available, letting AI do the work.
- **Keep the session interactive** — engineers can inspect progress at any time without stopping the session.
- **Stay local** — the bridge listens on `127.0.0.1:48152`, so nothing leaves your machine.
- **Use any MCP client** — Claude Code, Codex, Antigravity, and other compatible clients can all connect.


## Setup

**AI agent one-click install**

If your AI agent supports natural-language installation, just prompt it with:

```text
install https://github.com/Whfkl/Abaqus-Control-MCP
```

**1. Install the package**

You can install the package directly via Git, or from a cloned repository in your local directory.

**Option A: Remote Git Install (direct install)**

`uv` (recommended):

```bash
uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

Or `pip`:

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

---

**Option B: Local Directory Install (run inside the cloned project root)**

*   **Standard Local Install**

    `uv` (recommended):
    ```bash
    uv tool install .
    ```
    Or `pip`:
    ```bash
    pip install .
    ```

*   **Development Mode (editable install)**
    If you plan to modify the source code and have changes apply dynamically:

    `uv` (recommended):
    ```bash
    uv tool install --editable .
    ```
    Or `pip`:
    ```bash
    pip install -e .
    ```

Dependencies are declared in `pyproject.toml` — no `requirements.txt` needed. Any of the methods above will install the four CLI commands (`abaqus-control-mcp-server`, `abaqus-control-check`, `abaqus-control-doctor`, `abaqus-control-setup`) to your global environment or active virtual environment.

**2. Install the GUI plugin**

Run the following command to install automatically:

```bash
abaqus-control-setup
```

Alternatively, you can **manually** copy `abaqus_mcp_bridge/gui_plugin.py` from the project source to your Abaqus plugins directory (typically `~/abaqus_plugins/`).

> [!NOTE]
> You can override the target folder for both automatic and manual installations by setting the `ABAQUS_MCP_PLUGIN_DIR` environment variable.

**3. Start Abaqus/CAE, activate the plugin**

```
Plug-ins → Abaqus-Control-MCP → Start MCP Bridge
```

**4. Configure your MCP client**

Depending on the AI agent you use, add the MCP server configuration to the corresponding config file.

#### Option A: Claude Code (Claude CLI)

Add the following entry to the `mcpServers` section in `~/.claude.json`:

```json
"abaqus-control-mcp": {
  "command": "abaqus-control-mcp-server",
  "env": {
    "ABAQUS_MCP_HOST": "127.0.0.1",
    "ABAQUS_MCP_PORT": "48152",
    "ABAQUS_MCP_TIMEOUT": "120"
  }
}
```

> Note: Add to the `mcpServers` section in `~/.claude.json` (global) or under `projects.<path>.mcpServers` for a specific project. Claude Code starts the MCP server automatically when you open a session.

#### Option B: Antigravity (Gemini/Antigravity IDE)

Add the following entry to the `mcpServers` section in `~/.gemini/config/mcp_config.json`. Specifying an absolute path is recommended (replace `<Username>` with your system username):

```json
"abaqus-control-mcp": {
  "command": "abaqus-control-mcp-server",
  "env": {
    "ABAQUS_MCP_HOST": "127.0.0.1",
    "ABAQUS_MCP_PORT": "48152",
    "ABAQUS_MCP_TIMEOUT": "120"
  }
}
```

**5. Verify**

```bash
abaqus-control-check
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `ping` | Check connectivity + session state (models, viewports, PID) |
| `run_python` | Execute arbitrary Python code in the Abaqus kernel |
| `monitor_job_status` | List jobs or tail `.sta`/`.msg` for progress and diagnostics |
| `inspect_odb` | Open ODB read-only: sliced frames, variables with components |
| `capture_viewport` | Capture viewport screenshot as base64 (PNG/JPEG/TIFF/SVG) |
| `set_workdir` | Change the Abaqus working directory |

> Model creation, job submission, field/history output extraction — all go through `run_python`. Its error payload includes the traceback, error line, code excerpt, and recovery hints.

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
| `WinError 10061` Connection refused | The bridge service is not running in Abaqus/CAE. Please **first start Abaqus/CAE**, and select **Plug-ins -> Abaqus-Control-MCP -> Start MCP Bridge** from the top menu, then try again. |
| `Permission denied` / `os error 5` during install or update | An old `abaqus-control-mcp-server` process is still running in the background (used and locked by Claude Code/Cursor). Close the MCP client (such as Claude Code or Cursor) or manually terminate the process in Task Manager to release the file lock, then try installing again. |
| MCP client says `Connection closed` / Server crashes with `ModuleNotFoundError: No module named 'pydantic_core.core_schema'` | The dependency packages (e.g. `pydantic_core`) in the default Python environment (e.g. Python 3.13) selected by the `uv` tool runner are corrupted or missing DLLs on Windows. Force a reinstall using another installed Python version: `uv tool install --force --python 3.14 .` |
| `command not found: abaqus-control-mcp-server` | Reinstall or run `abaqus-control-doctor` |
| No output from server | Normal for stdio MCP server — it doesn't print to stdout |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | Use **Plug-ins** menu, not File → Run Script |
| Connection timed out | Start the Abaqus plugin **before** the MCP server |
| Model doesn't appear in GUI | Run `abaqus-control-check` — verify `"thread": "MainThread"` |
| Claude Code doesn't see MCP tools | 1. Run `claude mcp list` to check if `abaqus` is registered. 2. If not listed, add the MCP config as described in Step 4. 3. Restart Claude Code after any config change. |

## License

MIT — see [LICENSE](LICENSE).
