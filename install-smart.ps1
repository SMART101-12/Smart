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
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $python) { throw 'Python was installed but is not visible to this PowerShell session. Close PowerShell, reopen it, and run the installer again.' }
}

if (Test-Path $appRoot) { Remove-Item $appRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $appRoot, $binRoot | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $appRoot -Recurse -Force

$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
& $python.Source -m venv (Join-Path $appRoot '.venv')
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $appRoot 'requirements-iran-agent.txt')

$launcher = @"
@echo off
set "PYTHONPATH=$appRoot\src"
"$venvPython" -m smart.cli %*
"@
Set-Content -Path (Join-Path $binRoot 'smart.cmd') -Value $launcher -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable('Path','User')
if (-not (($userPath -split ';') -contains $binRoot)) {
    [Environment]::SetEnvironmentVariable('Path', (($userPath.TrimEnd(';') + ';' + $binRoot).Trim(';')), 'User')
}

$env:PYTHONPATH = Join-Path $appRoot 'src'
Write-Host ''
Write-Host 'Now configuring GitHub access.' -ForegroundColor Cyan
& $venvPython -m smart.setup_token

New-Item -ItemType Directory -Force -Path (Join-Path $appRoot 'runtime') | Out-Null

Write-Host ''
Write-Host 'SMART installation complete.' -ForegroundColor Green
Write-Host 'Close this PowerShell and open a new one.'
Write-Host 'Then run: smart start'
Write-Host 'Check:    smart status'
Write-Host 'Stop:     smart stop'
