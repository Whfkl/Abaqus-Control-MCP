$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "abaqus_plugins\abaqus_mcp_gui_plugin.py"
$targetDir = Join-Path $HOME "abaqus_plugins"
$target = Join-Path $targetDir "abaqus_mcp_gui_plugin.py"

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item -Path $source -Destination $target -Force

Write-Host "Installed Abaqus Control MCP GUI plugin to:"
Write-Host $target
Write-Host ""
Write-Host "Restart Abaqus/CAE, then use:"
Write-Host "Plug-ins -> Abaqus -> Start MCP GUI Agent"
Write-Host ""
Write-Host "Then start the MCP server:"
Write-Host "uv run abaqus-control-mcp-server"
