$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root 'python.exe'
$systemPython = 'C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe'

if (Test-Path (Join-Path $root '.venv\Scripts\python.exe')) {
    $candidate = Join-Path $root '.venv\Scripts\python.exe'
    & $candidate --version *> $null
    if ($LASTEXITCODE -eq 0) { $python = $candidate }
}

if (-not (Test-Path $python)) { $python = $systemPython }
if (-not (Test-Path $python)) { throw 'Python 3.12 was not found.' }

Write-Host '=== SMART: TSETMC raw MarketWatch update ==='
Write-Host 'Downloading raw file...'
& $python 'scripts\update_marketwatch.py'
if ($LASTEXITCODE -ne 0) { throw 'TSETMC download failed. Git was not changed.' }

$file = Get-ChildItem 'runtime\بورس_خام\marketwatch\*.gz' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $file) { throw 'Downloaded file was not found. Git was not changed.' }

git add -- "$($file.FullName.Substring($root.Length + 1))"
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host 'No new MarketWatch data to commit.'
    exit 0
}

git commit -m "data: update raw TSETMC marketwatch"
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }

Write-Host 'Synchronizing branch with origin...'
git pull --rebase origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) { throw 'git pull --rebase failed. Resolve Git state before retrying.' }

git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }

Write-Host '=== DONE: raw MarketWatch uploaded to GitHub ==='
