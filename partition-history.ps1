$ErrorActionPreference = "Stop"

Write-Host "=== SMART: validate and partition TSETMC history ==="

$python = "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe"
$script = "scripts\partition_tsetmc_history.py"

if (-not (Test-Path $python)) {
    throw "Python not found: $python"
}

Write-Host "Test symbol: Shbndr"
Write-Host "Reading full raw history and creating monthly partitions..."
& $python $script --symbol-hex "063406280646062f063106"
if ($LASTEXITCODE -ne 0) {
    throw "History partitioning failed. Git was not changed."
}

Write-Host "Adding only the test partition and validation output..."
git add -- "runtime/market_processed/history/شبندر" "runtime/market_processed/history_validation/شبندر"
if ($LASTEXITCODE -ne 0) {
    throw "git add failed."
}

if (git diff --cached --quiet) {
    Write-Host "No new partitioned data."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: partition Shbndr TSETMC history $date"
if ($LASTEXITCODE -ne 0) {
    throw "git commit failed."
}

Write-Host "Pushing test partitioned history to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) {
    throw "git push failed."
}

Write-Host "=== SHBNDER PARTITION TEST SUCCESSFUL ==="
