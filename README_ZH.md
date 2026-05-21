# Abaqus Control MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)

[English](README.md) | 中文

> **让 AI 可以直接驱动 Abaqus。** 只要描述你想要的模型——几何、材料、载荷、分析步——AI 就能在你的 Abaqus/CAE 会话里执行对应操作。

**Abaqus Control MCP** 把 Claude Code、Codex、Antigravity 以及其他 MCP 兼容客户端连接到正在运行的 Abaqus/CAE。你描述任务，AI 把它转成 Abaqus 操作，模型会实时更新。

> **旧版 Abaqus** 自带 Python 2。如果你的 Abaqus 使用 Python 2，请使用 [Python 2 兼容版本](https://github.com/hp283260133-bit/Abaqus-Control-MCP-abaqus2021)。

### 为什么选它？

- **直接在 GUI 中工作** — 操作会发生在当前 Abaqus 窗口中，几何、网格和结果都能即时看到。
- **流畅建模体验** — 直接通过桥接与 Abaqus 内核交互，让建模过程更顺手。
- **mdb、session、odb 以及其余 Python API 都可直接使用** — 让 AI 充分发挥能力。
- **保持会话可交互** — 工程师可以随时查看建模进展，无需中断会话。
- **仅本地运行** — 桥接只监听 `127.0.0.1:48152`，数据不会离开你的机器。
- **兼容常见 MCP 客户端** — Claude Code、Codex、Antigravity 等均可接入。

## 安装配置

**AI agent 一键安装**

如果你的 AI agent 支持自然语言安装，只需输入：

```text
安装 https://github.com/Whfkl/Abaqus-Control-MCP
```

**1. 安装包**

你可以通过远程 Git 直接安装，或者在克隆仓库后在本地目录安装。

**方式 A：远程 Git 安装 (直接安装)**

`uv`（推荐）：

```bash
uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

或 `pip`：

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

---

**方式 B：本地目录安装 (克隆仓库后在项目根目录下)**

*   **普通本地安装**

    `uv`（推荐）：
    ```bash
    uv tool install .
    ```
    或 `pip`：
    ```bash
    pip install .
    ```

*   **开发模式 (可编辑安装)**
    如果你想修改源码并让修改实时生效：

    `uv`（推荐）：
    ```bash
    uv tool install --editable .
    ```
    或 `pip`：
    ```bash
    pip install -e .
    ```

依赖已声明在 `pyproject.toml` 中，不需要 `requirements.txt`。上述任何一种方式都会安装四个 CLI 命令（`abaqus-control-mcp-server`、`abaqus-control-check`、`abaqus-control-doctor`、`abaqus-control-setup`）。

**2. 安装 GUI 插件**

运行以下命令自动安装：

```bash
abaqus-control-setup
```

或者，你也可以**手动**将项目源码中的 `abaqus_mcp_bridge/gui_plugin.py` 复制到 Abaqus 插件目录（通常为 `~/abaqus_plugins/`）。

> [!NOTE]
> 自动命令或手动安装的目标目录都可以通过设置 `ABAQUS_MCP_PLUGIN_DIR` 环境变量进行自定义覆盖。

**3. 启动 Abaqus/CAE，激活插件**

```
Plug-ins → Abaqus-Control-MCP → Start MCP Bridge
```

**4. 配置 MCP 客户端**

在 `~/.claude.json` 的 `mcpServers` 节点下添加：

```json
"abaqus-control-mcp v1.0": {
  "command": "abaqus-control-mcp-server",
  "env": {
    "ABAQUS_MCP_HOST": "127.0.0.1",
    "ABAQUS_MCP_PORT": "48152",
    "ABAQUS_MCP_TIMEOUT": "120"
  }
}
```

> 添加到 `~/.claude.json` 的 `mcpServers` 节点下（全局），或对应项目的 `projects.<path>.mcpServers` 下（仅该项目生效）。

Claude Code 会在会话启动时自动拉起 MCP 服务，无需手动启动。

**5. 验证**

```bash
abaqus-control-check
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `ping` | 检查连接 + 会话状态（模型、视口、PID） |
| `run_python` | 在 Abaqus 内核中执行任意 Python 代码 |
| `monitor_job_status` | 列出作业或读取 `.sta`/`.msg` 获取进度与诊断 |
| `inspect_odb` | 只读打开 ODB：帧裁剪，变量含分量信息 |
| `capture_viewport` | 截取视口图像为 base64（PNG/JPEG/TIFF/SVG） |
| `set_workdir` | 修改 Abaqus 工作目录 |

> 建模、提交作业、提取场/历史输出——全部通过 `run_python` 完成。它的错误返回会包含 traceback、错误行号、代码片段和修复提示。

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
| `WinError 10061` 由于目标计算机积极拒绝，无法连接 | 未在 Abaqus/CAE 中开启桥接服务。请**首先启动 Abaqus/CAE**，并在顶部菜单栏选择 **Plug-ins -> Abaqus-Control-MCP -> Start MCP Bridge** 开启服务，然后再试。 |
| MCP 客户端提示 `Connection closed` / 崩溃报错 `ModuleNotFoundError: No module named 'pydantic_core.core_schema'` | 这是由于 `uv` 安装工具在默认的 Python 隔离环境（如 Python 3.13）中依赖包（如 `pydantic_core`）编译异常或 DLL 缺失。可以通过强制指定系统上其他的 Python 版本（例如 Python 3.14）重新安装来解决：`uv tool install --force --python 3.14 .` |
| 找不到 `abaqus-control-mcp-server` | 重新安装或运行 `abaqus-control-doctor` |
| 服务端无输出 | 正常现象——stdio MCP 服务不向 stdout 输出日志 |
| `Module abaqusGui can only be used...` | 通过 **Plug-ins** 菜单启动，不要用 File → Run Script |
| 连接超时 | 先在 Abaqus 内启动插件，**再**启动 MCP 服务 |
| 模型未出现在 GUI 中 | 运行 `abaqus-control-check`，确认 `"thread": "MainThread"` |
| Claude Code 看不到 MCP 工具 | 1. 运行 `claude mcp list` 检查 `abaqus` 是否已注册。2. 如果未列出，按第 4 步添加 MCP 配置。3. 改完配置后重启 Claude Code。 |

## 许可证

MIT — 详见 [LICENSE](LICENSE)。
