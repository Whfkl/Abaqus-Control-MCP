# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[English](README.md) | 中文

> **让 AI 可以直接驱动 Abaqus。** 只要描述你想要的模型——几何、材料、载荷、分析步——AI 就能在你的 Abaqus/CAE 会话里执行对应操作。

**Abaqus Control MCP** 把 Claude、Cursor 以及其他 MCP 兼容客户端连接到正在运行的 Abaqus/CAE。你描述任务，AI 把它转成 Abaqus 操作，模型会实时更新。

> **旧版 Abaqus** 自带 Python 2。如果你的 Abaqus 使用 Python 2，请使用 [Python 2 兼容版本](https://github.com/hp283260133-bit/Abaqus-Control-MCP-abaqus2021)。

### 为什么选它？

- **直接在 GUI 中工作** — 操作会发生在当前 Abaqus 窗口中，几何、网格和结果都能即时看到。
- **流畅建模体验** — 直接通过桥接与 Abaqus 内核交互，让建模过程更顺手。
- **mdb、session、odb 以及其余 Python API 都可直接使用** — 让 AI 充分发挥能力。
- **保持会话可交互** — 工程师可以随时查看建模进展，无需中断会话。
- **仅本地运行** — 桥接只监听 `127.0.0.1:48152`，数据不会离开你的机器。
- **兼容常见 MCP 客户端** — Claude Code、Claude Desktop、Cursor 等都可以用同一套配置接入。

## 安装配置

**AI agent 一键安装**

如果你的 AI agent 支持自然语言安装，只需输入：

```text
安装 https://github.com/Whfkl/Abaqus-Control-MCP
```

**1. 安装包**

`uv`（推荐）：

```bash
uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

或 `pip`：

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

依赖写在 `pyproject.toml` 中，不需要 `requirements.txt`。两种方式都会安装四个 CLI 命令（`abaqus-control-mcp-server`、`abaqus-control-check`、`abaqus-control-doctor`、`abaqus-control-setup`）。

**2. 安装 GUI 插件**

```bash
abaqus-control-setup
```

将 `gui_plugin.py` 复制到 `~/abaqus_plugins/`。可通过 `ABAQUS_MCP_PLUGIN_DIR` 环境变量覆盖目标目录。

**3. 启动 Abaqus/CAE，激活插件**

```
Plug-ins → Abaqus-Control-MCP → Start MCP Bridge
```

**4. 配置 MCP 客户端**

`abaqus-control-setup` 会自动注册 MCP 服务器到 Claude Code（底层执行 `claude mcp add`）。如需手动注册：

```bash
# 全局生效（所有项目）
claude mcp add -s user -e ABAQUS_MCP_HOST=127.0.0.1 \
  -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 \
  abaqus /absolute/path/to/abaqus-control-mcp-server

# 仅当前项目
claude mcp add -s local -e ABAQUS_MCP_HOST=127.0.0.1 \
  -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 \
  abaqus /absolute/path/to/abaqus-control-mcp-server
```

> 必须使用可执行文件的绝对路径——Claude Code 的子进程可能不在你的 shell PATH 中。用 `which abaqus-control-mcp-server`（Windows 用 `where`）查看路径。

Claude Code 会在会话启动时自动拉起 MCP 服务，无需手动启动。

减少权限弹窗，在 `.claude/settings.json` 中白名单只读工具：

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

**Cursor** 等其他 MCP 客户端，请将服务器配置添加到各自的设置文件中。本 MCP 服务器使用标准 stdio 传输协议。

**5. 验证**

```bash
abaqus-control-check
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `ping` | 检查连接 + 会话状态（模型、视口、PID） |
| `run_python` | 在 Abaqus 内核中执行任意 Python 代码 |
| `inspect` | 检查对象路径，返回键名或公开属性 |
| `list_jobs` | 列出所有作业及状态、类型、模型 |
| `get_odb_info` | 只读打开 ODB：分析步、帧、可用变量 |
| `capture_viewport` | 截取视口图像为 base64（PNG/JPEG/TIFF/SVG） |
| `set_workdir` | 修改 Abaqus 工作目录 |

> 建模、提交作业、提取场/历史输出——全部通过 `run_python` 完成，拥有完整的 Abaqus API 访问权限，不受封装参数限制。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP 桥接主机地址 |
| `ABAQUS_MCP_PORT` | `48152` | TCP 桥接端口 |
| `ABAQUS_MCP_TIMEOUT` | `120` | 执行超时（秒） |
| `ABAQUS_MCP_PLUGIN_DIR` | `~/abaqus_plugins` | GUI 插件安装目录 |

## Python API

```python
from abaqus_mcp_bridge.client import AbaqusBridgeClient

client = AbaqusBridgeClient(timeout=60)
result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
print(result['return_value'])  # ['Model-1', ...]
```

## 故障排查

| 问题 | 解决方案 |
|-------|----------|
| 找不到 `abaqus-control-mcp-server` | 重新安装或运行 `abaqus-control-doctor` |
| 服务端无输出 | 正常现象——stdio MCP 服务不向 stdout 输出日志 |
| `Module abaqusGui can only be used...` | 通过 **Plug-ins** 菜单启动，不要用 File → Run Script |
| 连接超时 | 先在 Abaqus 内启动插件，**再**启动 MCP 服务 |
| 模型未出现在 GUI 中 | 运行 `abaqus-control-check`，确认 `"thread": "MainThread"` |
| Claude Code 看不到 MCP 工具 | 1. 运行 `claude mcp list` 检查 `abaqus` 是否已注册。2. 如果未列出，运行 `claude mcp add -s user -e ABAQUS_MCP_HOST=127.0.0.1 -e ABAQUS_MCP_PORT=48152 -e ABAQUS_MCP_TIMEOUT=120 abaqus /absolute/path/to/abaqus-control-mcp-server`。3. 改完配置后重启 Claude Code。 |

## 许可证

MIT — 详见 [LICENSE](LICENSE)。
