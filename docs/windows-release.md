# Windows release / Windows 发行包

The release ZIP contains `Abaqus-Control-MCP-Server.exe`, `abaqus_mcp_gui_plugin.py`, and a SHA-256 checksum for the executable. The server executable contains its own Python runtime; Abaqus/CAE is still required for the GUI plugin and simulations.

发行 ZIP 包含服务端 exe、GUI 插件及 exe 的 SHA-256 校验值。服务端无需另行安装 Python；GUI 插件和仿真仍需要 Abaqus/CAE。

## Install / 安装

1. Extract the ZIP to a stable directory. Do not run the executable by double-clicking it: it communicates with MCP clients over standard input and output.
2. Copy `abaqus_mcp_gui_plugin.py` to `%USERPROFILE%\abaqus_plugins\abaqus_mcp_gui_plugin.py` (create the directory if needed). If Abaqus uses a different plugin directory, copy it there instead.
3. Register the full path to `Abaqus-Control-MCP-Server.exe` as a **stdio** MCP server in Codex, Claude Code, or another client. For Codex, replace the example path:

   ```powershell
   codex mcp add abaqus-control-mcp --env ABAQUS_MCP_HOST=127.0.0.1 --env ABAQUS_MCP_PORT=48152 --env ABAQUS_MCP_TIMEOUT=120 -- "C:\Tools\Abaqus-Control-MCP\Abaqus-Control-MCP-Server.exe"
   ```

4. Start or restart Abaqus/CAE so it loads the plugin, then choose **Plug-ins → Abaqus-Control-MCP → Start MCP Bridge**.
5. Open a new client session and call `ping`, then `run_python` with `result = list(mdb.models.keys())`. The server exits when its MCP client disconnects.

安装顺序：解压发行包 → 将插件复制到 `%USERPROFILE%\abaqus_plugins\abaqus_mcp_gui_plugin.py` → 在 MCP 客户端中配置 exe 的完整路径 → 启动或重启 Abaqus/CAE 并启动桥接 → 开启新客户端会话调用 `ping` 和 `run_python`。exe 由客户端启动，不需要双击。

## Build from source / 从源码构建

On Windows, with [`uv`](https://docs.astral.sh/uv/) installed, run `powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_release.ps1` from the repository. The script creates a separate build environment, bundles the server with PyInstaller, and writes the ZIP plus its checksum under `dist/`.

在 Windows 上安装 `uv` 后，从仓库运行 `powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_release.ps1`。脚本使用独立构建环境，通过 PyInstaller 生成单文件 exe，并在 `dist/` 中生成 ZIP 和校验值。
