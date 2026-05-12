param(
	[string]$TargetDir = (Join-Path $HOME "abaqus_plugins"),
	[switch]$Force
)

$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "src\abaqus_mcp_bridge\gui_plugin.py"
if (-not (Test-Path $source)) {
	throw "Plugin source not found: $source"
}

$targetDir = $TargetDir
$target = Join-Path $targetDir "abaqus_mcp_gui_plugin.py"

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

if ((Test-Path $target) -and -not $Force) {
	$sourceBytes = [System.IO.File]::ReadAllBytes($source)
	$targetBytes = [System.IO.File]::ReadAllBytes($target)
	if ($sourceBytes.Length -eq $targetBytes.Length) {
		$identical = $true
		for ($i = 0; $i -lt $sourceBytes.Length; $i++) {
			if ($sourceBytes[$i] -ne $targetBytes[$i]) {
				$identical = $false
				break
			}
		}
		if ($identical) {
			Write-Host "Plugin already up to date at:"
			Write-Host $target
			Write-Host ""
			Write-Host "Restart Abaqus/CAE, then use:"
			Write-Host "Plug-ins -> Abaqus-Control-MCP -> Start MCP GUI Agent"
			exit 0
		}
	}
	throw "Plugin already exists at $target. Re-run with -Force to overwrite it."
}

Copy-Item -Path $source -Destination $target -Force

Write-Host "Installed Abaqus Control MCP GUI plugin to:"
Write-Host $target
Write-Host ""
Write-Host "Restart Abaqus/CAE, then use:"
Write-Host "Plug-ins -> Abaqus-Control-MCP -> Start MCP GUI Agent"
Write-Host ""
Write-Host "Then start the MCP server:"
Write-Host "abaqus-control-mcp-server"
