$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== SMART: partition all TSETMC historical data ==="

# The repository has previously encountered broken .venv launchers that could
# execute `python -c` but failed when launching a .py file. Therefore prefer
# the known-good system Python for this pipeline and verify it can execute the
# target script before changing Git state.
$pythonCandidates = @(
    "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe",
    (Join-Path $root ".venv\Scripts\python.exe")
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        Write-Host "Testing Python: $candidate"
        & $candidate "-c" "import sys; print(sys.executable)" *> $null
        if ($LASTEXITCODE -eq 0) {
            & $candidate "scripts\partition_all_tsetmc_history.py" *> $null
            if ($LASTEXITCODE -eq 0) {
                $python = $candidate
                break
            }
        }
    }
}

if (-not $python) {
    throw "No usable Python interpreter can execute scripts\partition_all_tsetmc_history.py. Git was not changed."
}

Write-Host "Using Python: $python"
Write-Host "Reading history universe and processing by InsCode..."

& $python "scripts\partition_all_tsetmc_history.py"
if ($LASTEXITCODE -ne 0) {
    throw "History partitioning completed with errors. Git was not changed."
}

git add -- "runtime/market_processed/history" "runtime/market_processed/history_validation"
if ($LASTEXITCODE -ne 0) { throw "git add failed." }

if (git diff --cached --quiet) {
    Write-Host "No new processed history changes."
    exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
git commit -m "data: partition TSETMC history $date"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

Write-Host "Pushing partitioned history to GitHub..."
git push origin agent/data-gap-recovery
if ($LASTEXITCODE -ne 0) { throw "git push failed." }

Write-Host "=== ALL HISTORY PARTITION SUCCESSFUL ==="
