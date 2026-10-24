# SMART Launcher - Windows PowerShell
# Finds Anaconda/Python automatically, prepares the environment,
# runs tests, starts the SMART web application, and opens the dashboard.

$ErrorActionPreference = "Stop"

# Always run from the folder containing this script.
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " SMART - Automatic Launcher" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

# ------------------------------------------------------------
# 1. Find Python
# ------------------------------------------------------------
$PythonCandidates = @(
    "C:\Users\PC101\anaconda3\python.exe",
    "$env:USERPROFILE\anaconda3\python.exe",
    "$env:USERPROFILE\miniconda3\python.exe",
    "C:\ProgramData\anaconda3\python.exe",
    "C:\ProgramData\miniconda3\python.exe"
)

$PythonPath = $null

foreach ($candidate in $PythonCandidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $PythonPath = (Resolve-Path -LiteralPath $candidate).Path
        break
    }
}

# If the expected Anaconda path was not found, search common locations.
if (-not $PythonPath) {
    Write-Host "Expected Anaconda path was not found. Searching common locations..." -ForegroundColor Yellow

    $SearchRoots = @(
        "$env:USERPROFILE",
        "C:\Users",
        "C:\ProgramData"
    ) | Where-Object { Test-Path $_ } | Select-Object -Unique

    foreach ($root in $SearchRoots) {
        try {
            $found = Get-ChildItem -Path $root -Filter "python.exe" -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.FullName -match "\\(anaconda3|miniconda3|Anaconda|Miniconda)\\python\.exe$"
                } |
                Select-Object -First 1

            if ($found) {
                $PythonPath = $found.FullName
                break
            }
        }
        catch {
            # Ignore inaccessible folders and continue searching.
        }
    }
}

if (-not $PythonPath) {
    Write-Host ""
    Write-Host "ERROR: Anaconda/Python executable could not be found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Expected path:"
    Write-Host "  C:\Users\PC101\anaconda3\python.exe"
    Write-Host ""
    Write-Host "Please install Anaconda or update the PythonCandidates section." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Python found:" -ForegroundColor Green
Write-Host "  $PythonPath"

# ------------------------------------------------------------
# 2. Check project files
# ------------------------------------------------------------
$Requirements = Join-Path $ProjectRoot "requirements.txt"
$SourceFolder = Join-Path $ProjectRoot "src"
$WebApp = Join-Path $SourceFolder "smart\webapp.py"

if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    Write-Host ""
    Write-Host "ERROR: requirements.txt was not found." -ForegroundColor Red
    Write-Host "Project root: $ProjectRoot"
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path -LiteralPath $SourceFolder -PathType Container)) {
    Write-Host ""
    Write-Host "ERROR: src folder was not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path -LiteralPath $WebApp -PathType Leaf)) {
    Write-Host ""
    Write-Host "WARNING: src\smart\webapp.py was not found." -ForegroundColor Yellow
    Write-Host "The launcher will still try to start uvicorn."
}

# ------------------------------------------------------------
# 3. Configure Python environment
# ------------------------------------------------------------
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "Python version:" -ForegroundColor Cyan
& $PythonPath --version

Write-Host ""
Write-Host "Python executable:" -ForegroundColor Cyan
& $PythonPath -c "import sys; print(sys.executable)"

# ------------------------------------------------------------
# 4. Install/update required packages
# ------------------------------------------------------------
Write-Host ""
Write-Host "Checking/installing requirements..." -ForegroundColor Cyan

& $PythonPath -m pip install -r $Requirements

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: requirements installation failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit $LASTEXITCODE
}

# ------------------------------------------------------------
# 5. Run tests
# ------------------------------------------------------------
Write-Host ""
Write-Host "Running SMART tests..." -ForegroundColor Cyan
& $PythonPath -m pytest -q

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Tests failed. SMART web application will NOT be started." -ForegroundColor Red
    Write-Host "Fix the failing tests and run this launcher again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "All tests passed." -ForegroundColor Green

# ------------------------------------------------------------
# 6. Start SMART web application
# ------------------------------------------------------------
$HostUrl = "http://127.0.0.1:8000/"

Write-Host ""
Write-Host "Starting SMART..." -ForegroundColor Green
Write-Host "Dashboard: $HostUrl"
Write-Host ""
Write-Host "Press CTRL+C to stop SMART." -ForegroundColor Yellow
Write-Host ""

# Open browser shortly after uvicorn starts.
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:8000/"
} | Out-Null

# Start the application in the foreground.
& $PythonPath -m uvicorn smart.webapp:app --reload --host 127.0.0.1 --port 8000
