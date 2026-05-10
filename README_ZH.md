# Abaqus Control MCP

[English](README.md) | 中文

> 从 Claude、Cursor 等 MCP 客户端直接连接并操纵正在运行的 Abaqus/CAE GUI 会话。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Abaqus 2024](https://img.shields.io/badge/Abaqus-2024-brightgreen)](#)

**Abaqus Control MCP** 是一个 Model Context Protocol (MCP) 桥接工具，让你可以从 Claude、Cursor 等 MCP 兼容的 AI 客户端直接操纵正在运行的 Abaqus/CAE GUI 会话。用自然语言描述分析需求，代码立即在活跃的 Abaqus 内核中执行——无需后台进程、无需脚本文件、无需轮询。

这是一个**本地可信自动化工具**，为想要将 AI 集成到 FEM 工作流中的工程师而设计。桥接默认监听 `127.0.0.1`，所有通信都留在你的机器上。

## 核心特性

- 🎯 **实时 GUI 控制**：直接操纵活跃的 Abaqus/CAE 会话——无需 noGUI 进程
- 💬 **自然语言驱动**：向 Claude 描述分析目标，它为你生成 Python 代码
- 🔌 **标准 MCP 接口**：兼容 Claude Desktop、Cursor、Codex 及所有支持 MCP 的客户端
- ⚡ **无需文件交互**：结果直接返回；无需保存/加载中间文件
- 🛡️ **本地隔离**：默认仅监听 `127.0.0.1`——适合可信工作站
- 📊 **完整 Python 访问**：访问完整的 Abaqus 2024 Python 3.10 环境及 `mdb`、`session` 对象

## 架构

```
MCP 客户端 (Claude, Cursor, ...)
    |
    | stdio JSON-RPC
    v
uv run abaqus-control-mcp-server
    |
    | localhost TCP (127.0.0.1:48152)
    v
Abaqus/CAE GUI 插件
    |
    | GUI 主线程队列 + abaqusGui.sendCommand(...)
    v
Abaqus/CAE 内核 Python 3.10
    |
    | mdb, session 对象
    v
活跃模型树 & 分析结果
```

GUI 插件在 Abaqus GUI 线程中运行，避免了与 `mdb` 和 `session` 的线程问题。请求被排队并由 GUI 主循环执行——安全且响应迅速。

## 快速开始（一句话版）

> **完成一次[安装](#安装)后**，每次使用 Abaqus Control MCP，你必须同时保持**两样东西在运行**：

<table>
<tr>
<th>① 在 Abaqus/CAE → Plug-ins 菜单中</th>
<th>② 在你的终端中</th>
</tr>
<tr>
<td>

```
Plug-ins -> Abaqus -> Start MCP GUI Agent
```

</td>
<td>

```bash
uv run abaqus-control-mcp-server
```

</td>
</tr>
</table>

> **就这么简单。** 两个都启动后，你的 MCP 客户端（Claude Desktop、Cursor 等）就能连接上来，用自然语言控制 Abaqus 了。

### 运行示意图

```
┌─────────────────────────────────────┐
│          你的电脑（终端侧）          │
│  ┌─────────────────────────────┐    │
│  │ uv run abaqus-control-     │    │
│  │       mcp-server           │    │
│  └──────────┬──────────────────┘    │
│             │ MCP stdio 协议        │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │   MCP 客户端 (Claude,       │    │
│  │   Cursor, ...)              │    │
│  └─────────────────────────────┘    │
└────────────────┬────────────────────┘
                 │ TCP (127.0.0.1:48152)
                 ▼
┌─────────────────────────────────────┐
│       Abaqus/CAE（GUI 侧）          │
│  ┌─────────────────────────────┐    │
│  │  Plug-ins → Abaqus → Start  │    │
│  │      MCP GUI Agent          │    │
│  └──────────┬──────────────────┘    │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │   Abaqus 内核 Python        │    │
│  │   (mdb, session 对象)       │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

## 安装

### 前置条件

- **Abaqus 2024** (Windows)
- **Python 3.10+** (用于本地环境，不是 Abaqus 内)
- **uv** (Python 包管理器 — [安装指南](https://docs.astral.sh/uv/getting-started/installation/))

### 安装步骤

1. **克隆仓库**

```bash
git clone https://github.com/Whfkl/Abaqus-Control-MCP.git
cd Abaqus-Control-MCP
```

2. **安装 Python 依赖**

```bash
uv sync
```

> **安装提示**：如果 `uv sync` 报错 `Expected a Python module at: src\abaqus_control_mcp\__init__.py`，说明构建后端 `uv_build` 从项目名错误推断包名。请改用 `hatchling` 构建后端，参考本仓库的 [pyproject.toml](pyproject.toml) 中的正确配置。

3. **安装 Abaqus/CAE GUI 插件**

打开 **PowerShell** 并运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_gui_plugin.ps1
```

插件被安装到 `C:\Users\<你的用户名>\abaqus_plugins\abaqus_mcp_gui_plugin.py`。

4. **重启 Abaqus/CAE**，然后通过菜单启动插件：

```
Plug-ins -> Abaqus -> Start MCP GUI Agent
```

5. **验证连接**

```powershell
uv run abaqus-control-check
```

预期输出（实际值因环境而异）：

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

> 如果看到 `Abaqus MCP agent is reachable.` 且包含 `"thread": "MainThread"`，说明连接成功。

## 使用方式

本项目需要**同时运行两个部分**：

| # | 什么 | 在哪里 | 怎么做 |
|---|------|--------|--------|
| 1 | **MCP GUI Agent 插件** | Abaqus/CAE 内部 | `Plug-ins -> Abaqus -> Start MCP GUI Agent` |
| 2 | **MCP Server** | 你的终端 | `uv run abaqus-control-mcp-server`（或通过 MCP 客户端配置） |

### 启动 MCP 服务

> **确保 Abaqus/CAE 正在运行**，且已通过插件菜单启动了 MCP GUI Agent，再启动 MCP Server。

在你的 MCP 客户端配置文件中（Claude Desktop、Cursor 等），添加：

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

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP 桥接的主机地址 |
| `ABAQUS_MCP_PORT` | `48152` | TCP 桥接端口 |
| `ABAQUS_MCP_TIMEOUT` | `120` | Python 执行超时时间（秒） |

> **Windows 路径提示**：`cwd` 字段请使用正斜杠（`D:/path/to/...`）或转义反斜杠（`D:\\path\\to\\...`），JSON 不允许未转义的反斜杠。

### 示例：用 Claude 生成悬臂梁模型

在 Claude Desktop 或 Cursor 中：

```
我：创建一个 1000mm x 100mm x 100mm 的钢制悬臂梁模型，网格约 1000 个单元。

Claude (使用 abaqus_execute_python 工具): 
  我会创建一个左端固定、顶端加载的悬臂梁模型。
  [通过 abaqus_execute_python 工具生成 Python 代码]

结果：模型立即出现在你活跃的 Abaqus/CAE 窗口中。
```

### Python API

```python
from abaqus_mcp_bridge.client import AbaqusBridgeClient

client = AbaqusBridgeClient(timeout=60)

# 执行单行表达式
result = client.execute("from abaqus import mdb; result = list(mdb.models.keys())")
print(result)  # {'mode': 'eval', 'ok': True, 'return_value': [...], ...}

# 执行多行代码，返回 result 变量
code = """
from abaqus import mdb
model = mdb.Model(name='Test')
result = {'model_name': model.name}
"""
result = client.execute(code)
print(result['return_value'])  # {'model_name': 'Test'}
```

## 可用的 MCP 工具

### `abaqus_ping`

检查 Abaqus 插件是否运行，获取当前会话状态：
- Python 版本和可执行文件路径
- 当前模型和视口
- GUI 线程名称（确认主线程执行）

### `abaqus_execute_python`

在活跃的 Abaqus/CAE 内核中执行 Python 代码：

- **单行表达式**：使用 `eval()`，返回表达式值
- **多行代码**：使用 `exec()`，返回 `result` 变量（如定义）
- **非序列化对象**：返回 `repr()` 和类型名称

响应包含：
- `mode`：`"eval"` 或 `"exec"`
- `ok`：成功时为 `true`
- `return_value`：结果
- `stdout`、`stderr`：捕获的输出

## 快速演示

```powershell
# 创建演示用悬臂梁模型
uv run abaqus-control-demo
```

一个 1000×100×100mm 的钢制悬臂梁模型（640 个单元）将出现在你活跃的 Abaqus/CAE 模型树中。

## 常见问题

**Q: 这是否适合生产环境？**

A: 本工具设计用于**单个工作站上的本地可信自动化**。桥接仅监听 `127.0.0.1`，执行权限与 Abaqus 进程相同。不要把端口暴露到共享网络或公网。

**Q: 支持 Abaqus Standard 和 Explicit 吗？**

A: GUI 插件适用于你机器上运行的任何 Abaqus/CAE GUI 实例。无论你使用 Standard 还是 Explicit 进行分析——插件都能对接 GUI 会话。

**Q: 如果我打开了多个 Abaqus 窗口怎么办？**

A: 插件对接**第一个**启动它的 GUI 实例。如果你需要控制其他会话，请重启该 Abaqus 窗口并再次启动插件。

## 安全 & 隐私

- 默认仅监听 `127.0.0.1`——不会主动暴露到公网。
- 这是"Abaqus Python 远程执行"——仅在可信本机环境中使用。
- 日志被写入系统临时目录，不会提交到仓库。
- 如果你执行的脚本中包含本机路径、用户名或模型名称，这些内容可能出现在结果或日志中。分享前请检查示例。

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| `uv sync` 报错：`Expected a Python module at: src\abaqus_control_mcp\__init__.py` | `uv_build` 构建后端错误地从项目名推断包名。改用 `hatchling` 构建后端，参考 [pyproject.toml](pyproject.toml) 的正确配置 |
| `uv sync` 提示找不到 `uv_build` | 安装 hatchling：`uv add --dev hatchling`，然后更新 `pyproject.toml` 使用 `hatchling.build` |
| `uv run abaqus-control-mcp-server` 无输出 | **这是正常的**，stdio MCP Server 不输出日志到 stdout |
| 按 Enter 时报 `JSON parse error` | 不要向 stdio 服务器输入空行 |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | 通过 **Plug-ins -> Abaqus -> Start MCP GUI Agent** 菜单启动插件，不要用 File -> Run Script |
| 连接 `timed out` 超时 | 检查插件日志 `$env:TEMP\abaqus_mcp_gui_plugin.log` |
| 模型未出现在 GUI 中 | 验证 `uv run abaqus-control-check` 返回 `"thread": "MainThread"` 和非空的 `models` 列表 |
| `uv` 命令未找到 | 从 https://docs.astral.sh/uv/getting-started/installation/ 安装 uv |

## 贡献

欢迎贡献！请：

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交清晰的 commit 信息
4. 开启 pull request

请确保所有改动都在干净的 Abaqus 2024 环境中测试过。

## 许可证

MIT License — 详见 [LICENSE](LICENSE) 文件。

---

**为 Abaqus 自动化而生，用 ❤️ 打造**

有问题？有建议？[提出 Issue](https://github.com/Whfkl/Abaqus-Control-MCP/issues) 或在 GitHub Discussions 中讨论。
