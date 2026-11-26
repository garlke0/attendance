# Starts everything for local work:
#   1. Docker Desktop (if it is not running) and waits for it
#   2. The Postgres container, and waits until it accepts connections
#   3. A window running the site (pages + API) on http://localhost:8000
#   4. A Cloudflare quick tunnel (public https link, needed for phone + GPS)
#   5. A control terminal (control.ps1) with the links
# Run it by double-clicking start.bat. Stop everything with stop.bat.

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
$Host.UI.RawUI.WindowTitle = "Attendance - starting"
$pidFile = Join-Path $env:TEMP "attendance-windows.txt"
$windowPids = @()

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
        Start-Sleep -Seconds 2
        $waited += 2
        Write-Host "." -NoNewline
    }
    Write-Host ""
}

# --- 2. Postgres ------------------------------------------------------------
Write-Host "[2/5] Starting the database..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed (see the message above)." }
$waited = 0
while ($true) {
    docker compose exec -T postgres sh -c 'pg_isready -U $POSTGRES_USER' *> $null
    if ($LASTEXITCODE -eq 0) { break }
    if ($waited -ge 60) { Fail "The database did not become ready within 60 seconds. Check: docker compose logs postgres" }
    Start-Sleep -Seconds 1
    $waited += 1
}

# --- 3. Site window ---------------------------------------------------------
# No --reload: starts faster and does not restart on file changes.
# After changing the code, close this window and run start.bat again.
Write-Host "[3/5] Starting the site..." -ForegroundColor Cyan
$serverCommand = "`$Host.UI.RawUI.WindowTitle = 'Attendance - server'; . '$activate'; uvicorn dev_server:app"
$w = Start-Process powershell.exe -PassThru -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $serverCommand
)
$windowPids += $w.Id

# --- 4. Tunnel ---------------------------------------------------------------
# Not waited for here: the control window shows the link when it is ready.
Write-Host "[4/5] Starting the Cloudflare tunnel..." -ForegroundColor Cyan
$log = Join-Path $env:TEMP "attendance-tunnel.log"
Remove-Item $log -ErrorAction SilentlyContinue
if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $tunnelCommand = "`$Host.UI.RawUI.WindowTitle = 'Attendance - tunnel'; cloudflared tunnel --url http://localhost:8000 --logfile '$log'"
    $w = Start-Process powershell.exe -PassThru -WorkingDirectory $root -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $tunnelCommand
    )
    $windowPids += $w.Id
    $tunnelLog = $log
} else {
    Write-Host "      cloudflared is not installed, skipping the tunnel." -ForegroundColor Yellow
    $tunnelLog = "none"
}

# --- 5. Control window ------------------------------------------------------
Write-Host "[5/5] Opening the control window..." -ForegroundColor Cyan
$controlScript = Join-Path $root "control.ps1"
$w = Start-Process powershell.exe -PassThru -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$controlScript`"", "`"$tunnelLog`""
)
$windowPids += $w.Id

# Saved for stop.bat (control window last, so it closes last)
$windowPids | Set-Content -Path $pidFile -Encoding ascii
