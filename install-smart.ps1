$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'SMART'
$appRoot = Join-Path $installRoot 'app'
$binRoot = Join-Path $installRoot 'bin'

Write-Host '=== SMART local agent installer ===' -ForegroundColor Cyan

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $python = $py }
}
if (-not $python) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Python is not installed and winget is unavailable. Install Python 3.12+ and run this installer again.' }
    Write-Host 'Python not found. Installing Python 3.12...' -ForegroundColor Yellow
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    throw 'Python was installed. Close PowerShell, reopen it, and run this installer again.'
}

if (Test-Path $appRoot) { Remove-Item $appRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $appRoot, $binRoot | Out-Null

# Copy the application source, but never copy a developer virtual environment.
# Copying .venv can leave a locked python.exe inside the installed app and make
# the subsequent venv creation fail with Access Denied.
Get-ChildItem -LiteralPath $source -Force |
    Where-Object { $_.Name -notin @('.venv', '.git', '__pycache__') } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $appRoot -Recurse -Force }

$venvPath = Join-Path $appRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

Write-Host 'Creating SMART virtual environment...' -ForegroundColor Yellow
& $python.Source -m venv $venvPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
    throw "Python failed to create the SMART virtual environment. Exit code: $LASTEXITCODE"
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -r (Join-Path $appRoot 'requirements-iran-agent.txt')
if ($LASTEXITCODE -ne 0) { throw 'SMART dependency installation failed.' }

$launcher = @"
@echo off
set "PYTHONPATH=$appRoot\src"
"$venvPython" -m smart.cli %*
"@
Set-Content -Path (Join-Path $binRoot 'smart.cmd') -Value $launcher -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable('Path','User')
if (-not $userPath) { $userPath = '' }
if (-not (($userPath -split ';') -contains $binRoot)) {
    $newPath = if ($userPath.Trim()) { $userPath.TrimEnd(';') + ';' + $binRoot } else { $binRoot }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
}

$env:PYTHONPATH = Join-Path $appRoot 'src'
Write-Host ''
Write-Host 'Now configuring GitHub access.' -ForegroundColor Cyan
& $venvPython -m smart.setup_token
if ($LASTEXITCODE -ne 0) { throw 'GitHub token setup failed.' }

New-Item -ItemType Directory -Force -Path (Join-Path $appRoot 'runtime') | Out-Null

Write-Host ''
Write-Host 'SMART installation complete.' -ForegroundColor Green
Write-Host 'Close this PowerShell and open a new one.'
Write-Host 'Then run: smart start'
Write-Host 'Check:    smart status'
Write-Host 'Stop:     smart stop'
