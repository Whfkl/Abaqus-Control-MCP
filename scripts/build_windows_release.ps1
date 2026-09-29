$ErrorActionPreference = 'Stop'

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'This release build must run on Windows.'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repo
try {
    $buildPython = Join-Path $repo '.venv-build\Scripts\python.exe'
    $pyinstaller = Join-Path $repo '.venv-build\Scripts\pyinstaller.exe'
    if (-not (Test-Path -LiteralPath $buildPython)) {
        & uv venv --python 3.13 .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
    }

    & uv pip install --python $buildPython . 'pyinstaller==6.22.3'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }

    & $pyinstaller --clean --noconfirm --onefile --console `
        --name Abaqus-Control-MCP-Server `
        --distpath dist --workpath build\pyinstaller --specpath build\pyinstaller `
        --collect-submodules anyio `
        --copy-metadata mcp --copy-metadata mcp-types `
        --copy-metadata abaqus-control-mcp `
        abaqus_mcp_bridge\__main__.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

    $version = (& $buildPython -c "from importlib.metadata import version; print(version('abaqus-control-mcp'))").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine the package version.' }
    $name = "Abaqus-Control-MCP-v$version-windows-x64"
    $releaseDir = Join-Path $repo "dist\$name"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo 'dist\Abaqus-Control-MCP-Server.exe') -Destination $releaseDir -Force
    Copy-Item -LiteralPath (Join-Path $repo 'abaqus_mcp_bridge\gui_plugin.py') -Destination (Join-Path $releaseDir 'abaqus_mcp_gui_plugin.py') -Force
    Copy-Item -LiteralPath (Join-Path $repo 'docs\windows-release.md') -Destination (Join-Path $releaseDir 'README.md') -Force
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE') -Destination $releaseDir -Force

    $exeHash = (Get-FileHash -LiteralPath (Join-Path $releaseDir 'Abaqus-Control-MCP-Server.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    "$exeHash  Abaqus-Control-MCP-Server.exe" | Set-Content -LiteralPath (Join-Path $releaseDir 'SHA256SUMS.txt') -Encoding ascii
    $zipPath = Join-Path $repo "dist\$name.zip"
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zipPath -Force
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$zipHash  $name.zip" | Set-Content -LiteralPath (Join-Path $repo "dist\$name.zip.sha256") -Encoding ascii
    Write-Output "Release ZIP: $zipPath"
    Write-Output "SHA-256: $zipHash"
}
finally {
    Pop-Location
}
