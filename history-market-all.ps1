$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== SMART: TSETMC ALL-MARKET full historical data update ==="

$pythonCandidates = @(
    "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe",
    (Join-Path $root ".venv\Scripts\python.exe")
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        Write-Host "Checking Python: $candidate"
        & $candidate "-c" "print('SMART PYTHON OK')" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    throw "No usable Python interpreter found. Git was not changed."
}

Write-Host "Using Python: $python"
Write-Host "Fetching full historical data for the complete current MarketWatch universe..."

& $python "scripts\fetch_tsetmc_history_all.py"
if ($LASTEXITCODE -ne 0) {
    throw "All-market historical download completed with errors. Git was not changed. Review the all-market report and rerun the command to resume."
}

Write-Host "Partitioning all fetched history into monthly files..."
& $python "scripts\partition_all_tsetmc_history.py"
if ($LASTEXITCODE -ne 0) {
    throw "All-market history partitioning failed. Git was not changed."
}

Write-Host "Adding all-market historical data to Git..."
git add -- "runtime/market_raw/history" "runtime/market_raw/history_universe" "runtime/market_processed/history" "runtime/market_processed/history_validation"
if ($LASTEXITCODE -ne 0) { throw "git add failed." }

if (git diff --cached --quiet) {
    Write-Host "No new all-market historical Git changes."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: update all-market TSETMC history $date"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

Write-Host "Pushing all-market historical data to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) { throw "git push failed." }

Write-Host "=== ALL-MARKET HISTORICAL UPDATE SUCCESSFUL ==="
