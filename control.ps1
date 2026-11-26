# Control window opened by start.ps1: activates the venv, shows the links,
# and shows the public (phone) link as soon as the tunnel is ready.
param([string]$TunnelLog = "none")

$Host.UI.RawUI.WindowTitle = "Attendance - control"
. (Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1")

Write-Host ""
Write-Host "Attendance system is running." -ForegroundColor Green
Write-Host ""
Write-Host "On this laptop:" -ForegroundColor Cyan
Write-Host "  Student page : http://localhost:8000"
Write-Host "  Doctor page  : http://localhost:8000/login.html"
Write-Host ""

if ($TunnelLog -ne "none") {
    Write-Host "Waiting for the public link" -NoNewline
    $url = $null
    for ($i = 0; $i -lt 40 -and -not $url; $i++) {
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
        if (Test-Path $TunnelLog) {
            $found = Select-String -Path $TunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
                     Select-Object -First 1
            if ($found) { $url = $found.Matches[0].Value }
        }
    }
    Write-Host ""
    if ($url) {
        Write-Host "From any phone (public link, changes every run):" -ForegroundColor Cyan
        Write-Host "  Student page : $url"
        Write-Host "  Doctor page  : $url/login.html"
        Write-Host "  Anyone with this link can open the site. Run stop.bat when you finish." -ForegroundColor Yellow
    } else {
        Write-Host "Public link not found yet. Look in the 'Attendance - tunnel' window." -ForegroundColor Yellow
    }
} else {
    Write-Host "No public link: cloudflared is not installed." -ForegroundColor Yellow
    Write-Host "  Install it once with: winget install --id Cloudflare.cloudflared"
}

Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  python add_doctor.py USERNAME    add a doctor / change password"
Write-Host "  docker compose ps                database status"
Write-Host ""
Write-Host "To stop everything (site, tunnel, database, Docker): double-click stop.bat"
Write-Host ""
