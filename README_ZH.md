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
MCP 客户端 (Claude Code, Claude Desktop, Cursor, ...)
    |
    | stdio JSON-RPC
    v
abaqus-control-mcp-server
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

## 快速开始

### 日常使用流程（安装一次后，每天只需两步）

每次使用 Abaqus Control MCP，你需要同时运行 **两个组件**：

> **步骤 A**（在 Abaqus/CAE 中启动插件）+ **步骤 B**（在终端启动 MCP Server）

<table>
<tr>
<th width="50%">步骤 A：在 Abaqus/CAE 中</th>
<th width="50%">步骤 B：在终端中</th>
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
<td>✅ 插件将在 Abaqus GUI 中启动<br>
    TCP 监听 127.0.0.1:48152</td>
<td>✅ MCP Server 启动 stdio 服务<br>
    等待 MCP 客户端连接</td>
</tr>
</table>

> **两个都启动后**，你的 MCP 客户端（Claude Code、Claude Desktop、Cursor 等）就能连接上来，用自然语言控制 Abaqus 了。

### 预期效果

```
终端侧:  abaqus-control-mcp-server  ← 持续运行
Abaqus:  Plug-ins → Abaqus → Start MCP GUI Agent  ← 持续运行
Claude/Claude Code:  用自然语言描述分析任务             ← 生成代码→发送→执行→返回结果
                                                      ↓
                                           模型在你的 Abaqus/CAE 中实时显示
```

> ⚠️ **重要**：必须先启动 Abaqus 侧的插件（步骤 A），再启动 MCP Server（步骤 B）。顺序反了会导致连接失败。

### 运行示意图

```
┌─────────────────────────────────────┐
│          你的电脑（终端侧）          │
│  ┌─────────────────────────────┐    │
│  │ abaqus-control-mcp-server   │    │
│  └──────────┬──────────────────┘    │
│             │ MCP stdio 协议        │
│             ▼                       │
│  ┌─────────────────────────────┐    │
│  │   MCP 客户端 (Claude Code,   │    │
│  │   Claude Desktop, Cursor)    │    │
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

### 方式 A：从 GitHub 安装（推荐）

无需克隆仓库 —— `pip` 直接从 GitHub 安装：

```bash
pip install git+https://github.com/Whfkl/Abaqus-Control-MCP.git
```

安装后 `abaqus-control-mcp-server` 和 `abaqus-control-check` 终端命令全局可用。

> **提示**：如果你使用 `uv`，可以改为运行 `uv tool install git+https://github.com/Whfkl/Abaqus-Control-MCP.git` 安装到独立环境。

### 方式 B：本地开发安装

1. **克隆并安装**

```bash
git clone https://github.com/Whfkl/Abaqus-Control-MCP.git
cd Abaqus-Control-MCP
pip install -e .
```

> **如果你用 uv 不是 pip**：运行 `uv sync`，然后用 `uv run abaqus-control-mcp-server` 启动服务。

### 安装 Abaqus/CAE GUI 插件

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
abaqus-control-check
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

如果还没安装，请先参考[安装](#安装)步骤。

安装完成后，日常使用只需参考上面的[快速开始](#快速开始)——每天只需 **两步**。

### 配置你的 MCP 客户端

> **确保 Abaqus/CAE 正在运行**，且已通过插件菜单启动了 MCP GUI Agent，再连接。

#### Claude Code

创建或编辑 `.claude/mcp.json`（项目级）或 `~/.claude/mcp.json`（全局）：

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

Claude Code 会在需要时自动启动服务，无需手动打开终端 —— 只需要确保 Abaqus 插件已在运行。

**配置权限（避免每次调用都弹确认）**

Claude Code 默认会在每次调用 MCP 工具时弹出确认提示。你可以将只读工具添加到白名单自动批准，同时保留高风险工具的确认提示。编辑 `~/.claude/settings.json` 或项目级 `.claude/settings.json`：

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

> 以下工具**不会**自动批准（每次调用仍需手动确认）：
> - `abaqus_execute_python` — 可在 Abaqus 中执行任意代码
> - `abaqus_submit_job` — 会提交并运行分析作业
> - `abaqus_get_viewport_image` — 会截取视口图像

> **使用 uv 而不 pip 安装的替代方案**：如果你克隆了仓库并使用 `uv`，请设置 `"command": "uv"`、`"args": ["run", "abaqus-control-mcp-server"]`，并添加 `"cwd": "D:/path/to/Abaqus-Control-MCP"`。

#### Claude Desktop / Cursor

在 MCP 客户端设置中添加：

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

#### 环境变量

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ABAQUS_MCP_HOST` | `127.0.0.1` | TCP 桥接的主机地址 |
| `ABAQUS_MCP_PORT` | `48152` | TCP 桥接端口 |
| `ABAQUS_MCP_TIMEOUT` | `120` | Python 执行超时时间（秒） |

> **Windows 路径提示**：如果使用 `uv` + `cwd` 方式，`cwd` 字段请使用正斜杠（`D:/path/to/...`）或转义反斜杠（`D:\\path\\to\\...`），JSON 不允许未转义的反斜杠。

### 示例：用 Claude 生成悬臂梁模型

在 Claude Code、Claude Desktop 或 Cursor 中：

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

| 工具 | 说明 |
|------|------|
| `abaqus_ping` | 检查连接 + 会话状态（模型、视口、PID） |
| `abaqus_execute_python` | 在 Abaqus 内核中执行任意 Python 代码 |
| `abaqus_get_model_info` | 列出所有模型的零件、材料、分析步、载荷、边界条件 |
| `abaqus_list_jobs` | 列出所有作业及状态、类型、模型关联 |
| `abaqus_submit_job` | 提交作业并等待完成 |
| `abaqus_get_odb_info` | 只读打开 ODB：分析步、帧、场/历史变量列表 |
| `abaqus_get_field_output` | 提取场输出数据（S/E/U/RF），返回最小值/最大值/平均值 |
| `abaqus_get_history_output` | 提取 ODB 历史输出时程曲线 |
| `abaqus_get_viewport_image` | 截取视口图像为 base64（PNG/JPEG/TIFF/SVG） |

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

响应包含 `mode`、`ok`、`return_value`、`stdout`、`stderr`。

### `abaqus_get_model_info`

返回会话中每个模型的结构化信息：零件名、材料名、分析步名、载荷、边界条件、相互作用、装配实例、视口详情。

### `abaqus_list_jobs`

返回所有 `mdb.jobs` 条目，含状态、类型、模型名、描述、CPU/内存设置。

### `abaqus_submit_job`

提交作业并阻塞直到完成。默认超时 600 秒。返回最终状态和 ODB 路径。

### `abaqus_get_odb_info`

只读打开 ODB 文件，返回：标题、描述、零件/实例名、分析步列表（含帧数/时间）、可用场/历史变量名。

### `abaqus_get_field_output`

从 ODB 提取场输出。参数：`odb_path`、`step_name`、`frame_index`、`output_variable`（如 "S"、"U"、"E"、"RF"）、`instance_name`、`position`。

返回汇总统计（最小值/最大值/平均值）及单元/节点值样本。

### `abaqus_get_history_output`

提取时程曲线。如果 `history_output_name` 为空，列出所有可用历史输出；否则返回 `[(time, value), ...]` 数据点。

### `abaqus_get_viewport_image`

截取视口图像为 base64。支持格式：`PNG`、`JPEG`、`TIFF`、`SVG`。`viewport_name` 留空则截取当前视口。

## MCP 资源

| URI | 说明 |
|-----|------|
| `abaqus://status` | 实时插件状态（模型、视口、PID、平台） |

## MCP 提示

| 提示 | 用途 |
|------|------|
| `abaqus_scripting_strategy` | MCP 环境下写 Abaqus Python 代码的最佳实践 |
| `abaqus_workflow_create_and_run` | 端到端工作流：创建 → 提交 → 后处理 |
| `abaqus_odb_postprocessing` | ODB 结果提取与解读指南 |

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
| `pip install` 报错找不到 `hatchling` | 安装 hatchling：`pip install hatchling`，然后重试 |
| `command not found: abaqus-control-mcp-server` | pip 安装的脚本未加入 PATH。尝试 `python -m abaqus_mcp_bridge.server` 或用 `pip install --user` 重装 |
| `abaqus-control-mcp-server` 无输出 | **这是正常的**，stdio MCP Server 不输出日志到 stdout |
| 按 Enter 时报 `JSON parse error` | 不要向 stdio 服务器输入空行 |
| `Module abaqusGui can only be used in Abaqus/CAE GUI` | 通过 **Plug-ins -> Abaqus -> Start MCP GUI Agent** 菜单启动插件，不要用 File -> Run Script |
| 连接 `timed out` 超时 | 检查插件日志 `$env:TEMP\abaqus_mcp_gui_plugin.log` |
| 模型未出现在 GUI 中 | 验证 `abaqus-control-check` 返回 `"thread": "MainThread"` 和非空的 `models` 列表 |
| Claude Code 找不到服务 | 确认 `abaqus-control-mcp-server` 在 PATH 中，在终端运行 `where abaqus-control-mcp-server` 验证。如果使用 `uv`，请在 MCP 配置中添加 `"cwd"` 指向仓库目录 |

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
