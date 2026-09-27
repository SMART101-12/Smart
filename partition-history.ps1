param(
    [Parameter(Mandatory=$true)]
    [string]$InsCode
)

$ErrorActionPreference = "Stop"

Write-Host "=== SMART: validate and partition TSETMC history ==="
Write-Host "InsCode: $InsCode"

$python = "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe"
$script = "scripts\partition_tsetmc_history.py"
$universe = "runtime\market_raw\history_universe\2026-08-18.json"

if (-not (Test-Path $python)) { throw "Python not found: $python" }
if (-not (Test-Path $universe)) { throw "History universe file not found: $universe" }

# Resolve symbol from InsCode using UTF-8 JSON. The symbol is never typed into this script.
$entry = (Get-Content -Raw -Encoding UTF8 $universe | ConvertFrom-Json).symbols |
    Where-Object { [string]$_.ins_code -eq $InsCode } |
    Select-Object -First 1

if (-not $entry) { throw "InsCode not found in history universe: $InsCode" }

$symbol = [string]$entry.symbol
$symbolHex = -join ([Text.Encoding]::UTF8.GetBytes($symbol) | ForEach-Object { $_.ToString('x2') })

Write-Host "Resolved symbol: $symbol"
Write-Host "Reading full raw history and creating monthly partitions..."
& $python $script --symbol-hex $symbolHex
if ($LASTEXITCODE -ne 0) {
    throw "History partitioning failed. Git was not changed."
}

Write-Host "Adding partitioned history and validation..."
git add -- "runtime/market_processed/history" "runtime/market_processed/history_validation"
if ($LASTEXITCODE -ne 0) { throw "git add failed." }

if (git diff --cached --quiet) {
    Write-Host "No new partitioned data."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: partition TSETMC history $InsCode $date"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

Write-Host "Pushing partitioned history to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) { throw "git push failed." }

Write-Host "=== PARTITION TEST SUCCESSFUL ==="
