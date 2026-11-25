# Starts everything for local work:
#   1. Docker Desktop (if it is not running) and waits for it
#   2. The Postgres container, and waits until it accepts connections
#   3. A window running the app (pages + API) on http://localhost:8000
#   4. A Cloudflare quick tunnel (public https link, needed for phone + GPS)
#   5. A control terminal in the project folder with the venv active,
#      showing the local links and the tunnel links
# Run it by double-clicking start.bat.

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
$Host.UI.RawUI.WindowTitle = "Attendance - starting"

function Fail($message) {
    Write-Host ""
    Write-Host "ERROR: $message" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

function Test-Docker {
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

# --- checks ---------------------------------------------------------------
$activate = Join-Path $root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) { Fail "No .venv found in $root. Create it first: python -m venv .venv" }
if (-not (Test-Path (Join-Path $root ".env"))) { Fail "No .env file found in $root." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker is not installed or not on PATH." }

# --- 1. Docker Desktop ------------------------------------------------------
Write-Host "[1/5] Checking Docker..." -ForegroundColor Cyan
if (-not (Test-Docker)) {
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerExe)) { Fail "Docker Desktop not found at $dockerExe. Start it by hand and run this again." }
    Write-Host "      Starting Docker Desktop (can take about a minute)..."
    Start-Process $dockerExe
    $waited = 0
    while (-not (Test-Docker)) {
        if ($waited -ge 180) { Fail "Docker did not start within 3 minutes. Open Docker Desktop and check it." }
        Start-Sleep -Seconds 3
        $waited += 3
        Write-Host "." -NoNewline
    }
    Write-Host ""
}
Write-Host "      Docker is running." -ForegroundColor Green

# --- 2. Postgres ------------------------------------------------------------
Write-Host "[2/5] Starting the database..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed (see the message above)." }
$waited = 0
while ($true) {
    docker compose exec -T postgres sh -c 'pg_isready -U $POSTGRES_USER' *> $null
    if ($LASTEXITCODE -eq 0) { break }
    if ($waited -ge 60) { Fail "The database did not become ready within 60 seconds. Check: docker compose logs postgres" }
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "." -NoNewline
}
Write-Host ""
Write-Host "      Database is ready." -ForegroundColor Green

# --- 3. App window ----------------------------------------------------------
Write-Host "[3/5] Starting the app..." -ForegroundColor Cyan
$serverCommand = "`$Host.UI.RawUI.WindowTitle = 'Attendance - server'; . '$activate'; uvicorn dev_server:app --reload"
Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $serverCommand
)

# --- 4. Tunnel ---------------------------------------------------------------
# A public https link to localhost:8000. Phones need https for the location check.
Write-Host "[4/5] Starting the Cloudflare tunnel..." -ForegroundColor Cyan
$tunnelUrl = $null
if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $log = Join-Path $env:TEMP "attendance-tunnel.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $tunnelCommand = "`$Host.UI.RawUI.WindowTitle = 'Attendance - tunnel (close this window to stop the public link)'; cloudflared tunnel --url http://localhost:8000 --logfile '$log'"
    Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $tunnelCommand
    )
    $waited = 0
    while (-not $tunnelUrl -and $waited -lt 40) {
        Start-Sleep -Seconds 2
        $waited += 2
        Write-Host "." -NoNewline
        if (Test-Path $log) {
            $found = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
                     Select-Object -First 1
            if ($found) { $tunnelUrl = $found.Matches[0].Value }
        }
    }
    Write-Host ""
    if ($tunnelUrl) {
        Write-Host "      Tunnel: $tunnelUrl" -ForegroundColor Green
    } else {
        Write-Host "      Tunnel started, but the link was not found yet. Look in the tunnel window." -ForegroundColor Yellow
    }
} else {
    Write-Host "      cloudflared is not installed, skipping the tunnel." -ForegroundColor Yellow
    Write-Host "      Install it once with:  winget install --id Cloudflare.cloudflared"
}

# --- 5. Control terminal ----------------------------------------------------
Write-Host "[5/5] Opening the control terminal..." -ForegroundColor Cyan
$controlLines = @(
    "`$Host.UI.RawUI.WindowTitle = 'Attendance - control'",
    ". '$activate'",
    "Write-Host ''",
    "Write-Host 'Attendance system is running.' -ForegroundColor Green",
    "Write-Host ''",
    "Write-Host 'On this laptop:' -ForegroundColor Cyan",
    "Write-Host '  Student page : http://localhost:8000'",
    "Write-Host '  Doctor page  : http://localhost:8000/login.html'",
    "Write-Host '  API docs     : http://localhost:8000/docs'",
    "Write-Host ''"
)
if ($tunnelUrl) {
    $controlLines += @(
        "Write-Host 'From any phone (public link, changes every run):' -ForegroundColor Cyan",
        "Write-Host '  Student page : $tunnelUrl'",
        "Write-Host '  Doctor page  : $tunnelUrl/login.html'",
        "Write-Host '  Anyone with this link can open the site. Close the tunnel window when you finish.' -ForegroundColor Yellow",
        "Write-Host ''"
    )
} else {
    $controlLines += @(
        "Write-Host 'No public link (tunnel not running). Phones cannot use the location check over http.' -ForegroundColor Yellow",
        "Write-Host ''"
    )
}
$controlLines += @(
    "Write-Host 'Useful commands:' -ForegroundColor Cyan",
    "Write-Host '  python -m pytest -q              run the tests'",
    "Write-Host '  python add_doctor.py USERNAME    add a doctor / change password'",
    "Write-Host '  docker compose ps                database status'",
    "Write-Host '  docker compose stop              stop the database (keeps the data)'",
    "Write-Host ''",
    "Write-Host 'To stop: close the Attendance - server and Attendance - tunnel windows.'",
    "Write-Host ''"
)
# One line, no double quotes inside: Windows PowerShell 5.1 mangles both
# when passing a -Command argument to a new window.
$controlCommand = $controlLines -join "; "
Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $controlCommand
)

Write-Host ""
Write-Host "Done. This window will close in 3 seconds." -ForegroundColor Green
Start-Sleep -Seconds 3
