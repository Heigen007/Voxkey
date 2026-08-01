# Build dist\Voxkey.exe from source.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# There is nothing secret in the build. No API key is ever compiled in - the
# app asks for one on first run and stores it encrypted under %APPDATA%.
# CI runs these exact steps on a tag; see .github/workflows/release.yml.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads a .ps1 without
# a BOM as ANSI, so non-ASCII characters here break the parser.

$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $base

$python = if (Test-Path "$base\.venv\Scripts\python.exe") { "$base\.venv\Scripts\python.exe" } else { 'python' }

Write-Host '=== Voxkey: build ===' -ForegroundColor Cyan

Write-Host '-> installing build dependencies'
& $python -m pip install -e ".[dev]" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw "pip install exited with code $LASTEXITCODE" }

Write-Host '-> running tests'
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'tests failed - not building a binary from broken code' }

Write-Host '-> generating icon'
& $python -m voxkey.icon
if ($LASTEXITCODE -ne 0) { throw "icon generation exited with code $LASTEXITCODE" }

Write-Host '-> pyinstaller (a minute or two)'
& $python -m PyInstaller `
    --onefile `
    --noconsole `
    --noupx `
    --clean `
    --noconfirm `
    --name Voxkey `
    --icon "$base\icon.ico" `
    --collect-all sounddevice `
    --collect-all pystray `
    --paths "$base\src" `
    "$base\packaging\voxkey_app.py"
if ($LASTEXITCODE -ne 0) { throw "pyinstaller exited with code $LASTEXITCODE" }

$exe = "$base\dist\Voxkey.exe"
if (-not (Test-Path $exe)) { throw 'Build reported success but dist\Voxkey.exe is missing' }

$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$mb = [Math]::Round((Get-Item $exe).Length / 1MB, 1)

Write-Host ''
Write-Host "Done: $exe ($mb MB)" -ForegroundColor Green
Write-Host "SHA256: $hash"
