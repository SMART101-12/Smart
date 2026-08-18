$ErrorActionPreference = "Stop"

Write-Host "=== SMART: TSETMC raw MarketWatch update ==="

$python = "C:\Users\s.nekounam\AppData\Local\Programs\Python\Python312\python.exe"
$script = "scripts\update_marketwatch.py"

Write-Host "Downloading raw file..."

& $python $script
if ($LASTEXITCODE -ne 0) {
    throw "TSETMC download failed. Git was not changed."
}

$file = Get-ChildItem "runtime\market_raw\marketwatch\*.gz" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $file) {
    throw "Downloaded file was not found. Git was not changed."
}

Write-Host "File: $($file.FullName)"
Write-Host "Size: $($file.Length) bytes"

Write-Host "Adding file to Git..."
git add -- "runtime/market_raw/marketwatch"

if ($LASTEXITCODE -ne 0) {
    throw "git add failed."
}

if (-not (git diff --cached --quiet)) {
    $date = Get-Date -Format "yyyy-MM-dd"
    git commit -m "data: update TSETMC marketwatch $date"

    if ($LASTEXITCODE -ne 0) {
        throw "git commit failed."
    }

    Write-Host "Pushing to GitHub..."
    git push origin agent/data-gap-recovery

    if ($LASTEXITCODE -ne 0) {
        throw "git push failed."
    }

    Write-Host "=== UPDATE SUCCESSFUL ==="
}
else {
    Write-Host "No new Git changes."
}
