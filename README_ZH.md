# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[English](README.md) | 中文

> **像聊天一样控制 Abaqus。** 描述你要做的有限元分析——几何、材料、载荷——AI 直接在活跃的 Abaqus/CAE 里执行代码。不用写脚本，不用中转文件，不用开 `noGUI`。

**Abaqus Control MCP** 把 Claude、Cursor 等 MCP 兼容的 AI 工具接入运行中的 Abaqus/CAE。你跟 AI 对话，AI 操控 Abaqus，模型实时变化。

### 为什么选它？

- **实时 GUI 反馈** — 代码跑在你的活跃 Abaqus 窗口里，每建一个零件、每画一次网格都立即可见。
- **零中间文件** — 结果通过 TCP 桥接直接返回，不产生散落一地的 `.py` 和 `.odb`。
- **完整 API 访问** — `mdb`、`session` 和全部 Abaqus Python 模块全部可用，没有沙箱，没有限制。
- **本地隔离** — 桥接只监听 `127.0.0.1:48152`，所有数据不出你的工作站。
- **标准 MCP 协议** — 支持 Claude Code、Claude Desktop、Cursor 和所有 MCP 兼容客户端，丢个配置就能用。

## 安装配置

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

Claude Code 用户创建 `~/.claude/.mcp.json`（全局）或 `<项目>/.mcp.json`（单项目）：

```json
{
  "mcpServers": {
    "abaqus": {
      "command": "/absolute/path/to/abaqus-control-mcp-server",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "120"
      }
    }
  }
}
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
      "mcp__abaqus__get_model_info",
      "mcp__abaqus__list_jobs",
      "mcp__abaqus__get_odb_info",
      "mcp__abaqus__get_field_output",
      "mcp__abaqus__get_history_output"
    ]
  }
}
```

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
| `get_model_info` | 列出零件、材料、分析步、载荷、边界条件 |
| `list_jobs` | 列出所有作业及状态、类型、模型 |
| `submit_job` | 提交作业并等待完成 |
| `get_odb_info` | 只读打开 ODB：分析步、帧、可用变量 |
| `get_field_output` | 提取场输出（S/E/U/RF），返回最小值/最大值/平均值 |
| `get_history_output` | 提取 ODB 历史输出时程曲线 |
| `capture_viewport` | 截取视口图像为 base64（PNG/JPEG/TIFF/SVG） |
| `set_workdir` | 修改 Abaqus 工作目录 |

## MCP 提示

| 提示 | 用途 |
|------|------|
| `abaqus_scripting_strategy` | Abaqus 脚本最佳实践 + 错误恢复 SOP |
| `abaqus_workflow_create_and_run` | 端到端：建模 → 提交 → 后处理 |
| `abaqus_odb_postprocessing` | ODB 结果提取与解读指南 |

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
| Claude Code 看不到 MCP 工具 | `.mcp.json` 中用绝对路径，改完配置后重启 Claude Code |

## 安全

仅监听 `127.0.0.1`。以 Abaqus 进程同等权限执行 Python。日志写入系统临时目录。分享前请检查输出中是否包含本机路径或模型名称。

## 许可证

MIT — 详见 [LICENSE](LICENSE)。
