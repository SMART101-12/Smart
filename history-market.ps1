$ErrorActionPreference = "Stop"

Write-Host "=== SMART: TSETMC full historical data update ==="

$python = "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe"
$script = "scripts\fetch_tsetmc_history.py"

if (-not (Test-Path $python)) {
    throw "Python not found: $python"
}

Write-Host "Fetching full daily history for configured symbols..."
& $python $script
if ($LASTEXITCODE -ne 0) {
    throw "Historical TSETMC download failed. Git was not changed."
}

Write-Host "Adding historical data to Git..."
git add -- "runtime/market_raw/history" "runtime/market_raw/history_universe"
if ($LASTEXITCODE -ne 0) {
    throw "git add failed."
}

if (git diff --cached --quiet) {
    Write-Host "No new historical Git changes."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: update TSETMC historical prices $date"
if ($LASTEXITCODE -ne 0) {
    throw "git commit failed."
}

Write-Host "Pushing historical data to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) {
    throw "git push failed."
}

Write-Host "=== HISTORICAL UPDATE SUCCESSFUL ==="
