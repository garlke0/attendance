# The Cafe - stop everything (via stop.bat). Your data stays: this uses "stop", never "down -v".

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "==> Stopping the website..." -ForegroundColor Cyan
$conns = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -eq "node") {   # only stop Node.js, never some other program on port 3000
        Stop-Process -Id $proc.Id -Force
        Write-Host "    stopped node (pid $($proc.Id))"
    }
}

Write-Host "==> Stopping database, Redis and API (data is kept)..." -ForegroundColor Cyan
docker compose stop

Write-Host ""
Write-Host "  Everything is stopped. Your data is safe." -ForegroundColor Green
Write-Host "  Start again with start.bat"
Write-Host ""
Read-Host "Press Enter to close"
