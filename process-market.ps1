$ErrorActionPreference = "Stop"

Write-Host "=== SMART: process raw TSETMC MarketWatch ==="

$python = "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe"
$script = "scripts\process_marketwatch.py"

if (-not (Test-Path $python)) {
    throw "Python not found: $python"
}

Write-Host "Parsing latest raw MarketWatch file..."
& $python $script
if ($LASTEXITCODE -ne 0) {
    throw "MarketWatch processing failed. Git was not changed."
}

Write-Host "Adding generated symbol data..."
git add -- "runtime/market_raw/stocks" "runtime/market_raw/universe" "runtime/market_processed"
if ($LASTEXITCODE -ne 0) {
    throw "git add failed."
}

if (git diff --cached --quiet) {
    Write-Host "No new processed data."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: process TSETMC marketwatch $date"
if ($LASTEXITCODE -ne 0) {
    throw "git commit failed."
}

Write-Host "Pushing processed market data to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) {
    throw "git push failed."
}

Write-Host "=== MARKET PROCESSING SUCCESSFUL ==="
