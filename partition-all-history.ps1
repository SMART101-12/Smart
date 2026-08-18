$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "=== SMART: partition all TSETMC historical data ==="

# Known project lesson: this machine has had a broken .venv Python launcher that
# could run `python -c` but failed when launching .py files. Do not pre-run the
# partition script as a probe. Instead select an interpreter, then run the
# partition script exactly once and inspect its exit code.
$pythonCandidates = @(
    "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe",
    (Join-Path $root ".venv\Scripts\python.exe")
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        Write-Host "Checking Python: $candidate"
        $probe = @(& $candidate "-c" "import sys; print(sys.executable)" 2>&1)
        $probeExit = $LASTEXITCODE
        if ($probeExit -eq 0) {
            $probe | ForEach-Object { Write-Host $_ }
            $python = $candidate
            break
        }
        Write-Host "Python probe failed: exit=$probeExit"
    }
}

if (-not $python) {
    throw "No usable Python interpreter was found. Git was not changed."
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
