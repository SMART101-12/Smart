$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA 'SMART'
$appRoot = Join-Path $installRoot 'app'
$binRoot = Join-Path $installRoot 'bin'

Write-Host '=== SMART local agent installer ===' -ForegroundColor Cyan

# This Windows setup has a working `python` command even though direct
# execution of the absolute python.exe path can be blocked. Prefer the
# command resolver and invoke Python by command name.
$pythonCommand = $null
foreach ($name in @('python', 'py')) {
    try {
        if ($name -eq 'py') { $versionText = & py -3.12 --version 2>&1 } else { $versionText = & python --version 2>&1 }
        if ($LASTEXITCODE -eq 0 -and $versionText -match 'Python 3\.(12|13)') {
            $pythonCommand = $name
            break
        }
    } catch { }
}

if (-not $pythonCommand) {
    throw 'A working Python 3.12/3.13 command was not found. Verify `python --version` or `py --version` in PowerShell.'
}

Write-Host ("Using Python command: " + $pythonCommand) -ForegroundColor Green

if (Test-Path $appRoot) { Remove-Item $appRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $appRoot, $binRoot | Out-Null

# Copy the application source, but never copy a developer virtual environment.
Get-ChildItem -LiteralPath $source -Force |
    Where-Object { $_.Name -notin @('.venv', '.git', '__pycache__') } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $appRoot -Recurse -Force }

$venvPath = Join-Path $appRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

Write-Host 'Creating SMART virtual environment...' -ForegroundColor Yellow
if ($pythonCommand -eq 'py') { & py -3.12 -m venv $venvPath } else { & python -m venv $venvPath }
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
