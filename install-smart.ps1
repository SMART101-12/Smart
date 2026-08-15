$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'SMART'
$appRoot = Join-Path $installRoot 'app'
$binRoot = Join-Path $installRoot 'bin'

Write-Host '=== SMART local agent installer ===' -ForegroundColor Cyan

# The user's Windows environment has a working Python Launcher (`py`), while
# direct execution of python.exe can be blocked by local Windows policy.
# Use the launcher directly and do not probe with where.exe/Get-Command.
$pyVersion = (& py -3.12 --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pyVersion -notmatch 'Python 3\.12') {
    throw "Python 3.12 is required. `py -3.12 --version` failed or returned: $pyVersion"
}
Write-Host ("Using Python: " + $pyVersion) -ForegroundColor Green

if (Test-Path $appRoot) { Remove-Item $appRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $appRoot, $binRoot | Out-Null

# Copy application source, excluding local/dev state.
Get-ChildItem -LiteralPath $source -Force |
    Where-Object { $_.Name -notin @('.venv', '.git', '__pycache__') } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $appRoot -Recurse -Force }

$venvPath = Join-Path $appRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

Write-Host 'Creating SMART virtual environment...' -ForegroundColor Yellow
& py -3.12 -m venv $venvPath
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
    throw "Python failed to create the SMART virtual environment. Exit code: $LASTEXITCODE"
}

# Verify the venv interpreter before doing any package work.
$venvVersion = (& $venvPython --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "SMART virtual-environment Python could not be executed: $venvVersion" }
Write-Host ("SMART venv: " + $venvVersion) -ForegroundColor Green

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -r (Join-Path $appRoot 'requirements-iran-agent.txt')
if ($LASTEXITCODE -ne 0) { throw 'SMART Iran-agent dependency installation failed.' }

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

if ($env:SMART_SKIP_GITHUB_SETUP -ne '1') {
    Write-Host ''
    Write-Host 'Now configuring GitHub access.' -ForegroundColor Cyan
    & $venvPython -m smart.setup_token
    if ($LASTEXITCODE -ne 0) { throw 'GitHub token setup failed.' }
} else {
    Write-Host 'Skipping GitHub token setup (test mode).' -ForegroundColor DarkYellow
}

New-Item -ItemType Directory -Force -Path (Join-Path $appRoot 'runtime') | Out-Null

Write-Host ''
Write-Host 'SMART installation complete.' -ForegroundColor Green
Write-Host 'Close this PowerShell and open a new one.'
Write-Host 'Then run: smart start'
Write-Host 'Check:    smart status'
Write-Host 'Stop:     smart stop'
