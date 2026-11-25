# The Cafe - start everything (run by start.bat).
#
# This window becomes "The Cafe - API": you watch every command run here, and when it's done it
# stays open in api\ with .venv active, ready for pytest, alembic, docker compose logs...
# A second PowerShell window, "The Cafe - website", runs Next.js. Then Brave opens every page.
#
# start.bat dot-sources this file (". start.ps1") so the .venv stays active in this window afterwards.
# Works in Windows PowerShell 5.1 (built into Windows). ASCII only on purpose.

$Slug = "the-cafe"                                   # the cafe to open
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Api  = Join-Path $Root "api"
$Web  = Join-Path $Root "web"
$Host.UI.RawUI.WindowTitle = "The Cafe - API"
Set-Location $Root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Show($cmd)  { Write-Host "PS $((Get-Location).Path)> $cmd" -ForegroundColor DarkGray }   # print the command, like typing it

function Test-Url($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -lt 500
    } catch {
        $resp = $_.Exception.Response            # a 4xx still means the server is up
        if ($resp) { return ([int]$resp.StatusCode -lt 500) }
        return $false
    }
}

function Wait-For($test, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try { if (& $test) { Write-Host ""; return $true } } catch { }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
    Write-Host ""
    return $false
}

try {
    Write-Host ""
    Write-Host "  The Cafe - starting up" -ForegroundColor Yellow

    # 1. Docker Desktop
    Step "Docker Desktop"
    Show "docker info"
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        $dockerApp = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (-not (Test-Path $dockerApp)) { throw "Docker Desktop isn't installed (looked in $dockerApp)." }
        Write-Host "Docker isn't running. Opening Docker Desktop (can take a minute)" -ForegroundColor Yellow
        Show "Start-Process '$dockerApp'"
        Start-Process $dockerApp
        if (-not (Wait-For { docker info *> $null; $LASTEXITCODE -eq 0 } 180)) {
            throw "Docker didn't start in 3 minutes. Open Docker Desktop yourself, then run start.bat again."
        }
    }
    Write-Host "Docker is running" -ForegroundColor Green

    # 2. Database, Redis, API  ("up -d" keeps your data. Never "down -v".)
    Step "Database, Redis and API"
    Show "docker compose up -d"
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed. Try: docker compose logs api" }

    Write-Host "Waiting for the API (migrations and startup safety checks run first)" -NoNewline
    if (-not (Wait-For { Test-Url "http://127.0.0.1:8000/health" } 120)) {
        Show "docker compose logs api --tail 20"
        docker compose logs api --tail 20
        throw "The API didn't come up. The lines above say why (look for 'Refusing to start')."
    }
    Show "docker compose ps"
    docker compose ps
    Write-Host "API is up: http://127.0.0.1:8000" -ForegroundColor Green

    # 3. The website, in a second PowerShell window you can watch and stop with Ctrl+C
    Step "Website (Next.js)"
    if (-not (Test-Path (Join-Path $Web "node_modules\next"))) {
        Write-Host "First run: installing website packages" -ForegroundColor Yellow
        Set-Location $Web
        Show "npm install"
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
        Set-Location $Root
    }
    if (Test-Url "http://localhost:3000") {
        Write-Host "The website is already running" -ForegroundColor Green
    } else {
        Show "(new window) cd web ; npm run dev"
        $webCommand = "`$Host.UI.RawUI.WindowTitle = 'The Cafe - website'; Write-Host 'PS> npm run dev' -ForegroundColor DarkGray; npm run dev"
        Start-Process powershell -WorkingDirectory $Web -ArgumentList @("-NoExit", "-Command", $webCommand)
        Write-Host "Waiting for the website" -NoNewline
        if (-not (Wait-For { Test-Url "http://localhost:3000/t/$Slug" } 120)) {
            throw "The website didn't come up. Look at the 'The Cafe - website' window for the error."
        }
    }
    Write-Host "Website is up: http://localhost:3000" -ForegroundColor Green

    # 4. Brave with every page in one window (default browser if Brave isn't installed)
    Step "Brave"
    $pages = @(
        "http://localhost:3000/t/$Slug",            # customer site
        "http://localhost:3000/t/$Slug/staff",      # order board (login)
        "http://localhost:3000/t/$Slug/admin",      # admin panel (login)
        "http://127.0.0.1:8000/docs"                # FastAPI docs
    )
    $brave = @(
        (Join-Path $env:ProgramFiles "BraveSoftware\Brave-Browser\Application\brave.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "BraveSoftware\Brave-Browser\Application\brave.exe"),
        (Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\Application\brave.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($brave) {
        Show "brave --new-window (4 pages)"
        Start-Process $brave -ArgumentList (@("--new-window") + $pages)
    } else {
        Write-Host "Brave not found, using the default browser" -ForegroundColor Yellow
        foreach ($p in $pages) { Start-Process $p; Start-Sleep -Milliseconds 400 }
    }

    # 5. Leave this window ready to work: api\ with .venv active
    Step "Terminal ready"
    Set-Location $Api
    Show ".venv\Scripts\Activate.ps1"
    . (Join-Path $Api ".venv\Scripts\Activate.ps1")

    Write-Host ""
    Write-Host "  All running!" -ForegroundColor Green
    Write-Host "  Customer site : http://localhost:3000/t/$Slug"
    Write-Host "  Order board   : http://localhost:3000/t/$Slug/staff"
    Write-Host "  Admin panel   : http://localhost:3000/t/$Slug/admin"
    Write-Host "  FastAPI docs  : http://127.0.0.1:8000/docs"
    Write-Host ""
    Write-Host "  This window: api\ with .venv active. Try: python -m pytest -q" -ForegroundColor Yellow
    Write-Host "  Stop everything: double-click stop.bat" -ForegroundColor Yellow
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Host "XX $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "   This window stays open so you can look around and fix it." -ForegroundColor Red
}
