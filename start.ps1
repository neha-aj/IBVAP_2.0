# One-command startup for the IBVAP+Thermal clone (backend + frontend).
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File "C:\Users\Neha AJ\Desktop\prototype2\Lux\IBVAP+Thermal\start.ps1"
#
# This stack's backend runs under its own Compose project name
# (COMPOSE_PROJECT_NAME=ibvap-thermal, set in backend\.env) so its
# containers/network/volumes never collide with the sibling IBVAP
# (non-thermal) stack's -- but both still bind the SAME host ports
# (8080/5173), so only one of the two can be up at a time. This script
# stops the sibling stack(s) first, same as IBVAP's own start.ps1 does
# for this one.

$root = $PSScriptRoot
$dockerDesktopExe = "C:\Users\Neha AJ\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"

function Test-DockerRunning {
    try { docker info *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}

# --- 1. Make sure Docker Desktop is running ---
if (-not (Test-DockerRunning)) {
    Write-Host "Starting Docker Desktop..." -ForegroundColor Cyan
    Start-Process $dockerDesktopExe
    $waited = 0
    while (-not (Test-DockerRunning)) {
        if ($waited -ge 90) {
            Write-Host "Docker still isn't up after 90s -- open Docker Desktop manually and re-run this script." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Seconds 3
        $waited += 3
    }
    Write-Host "Docker is up." -ForegroundColor Green
} else {
    Write-Host "Docker is already running." -ForegroundColor Green
}

# --- 2. Free the shared ports from any other project's stack, if it's up ---
$otherStacks = @(
    "C:\Users\Neha AJ\Desktop\prototype2\Lux\IBVAP\backend",
    "C:\Users\Neha AJ\Desktop\prototype2\M0-M3\ibvap"
)
foreach ($otherStack in $otherStacks) {
    if (Test-Path "$otherStack\docker-compose.yml") {
        $running = docker ps --filter "name=backend-nginx-1" --filter "name=ibvap-nginx-1" --format "{{.Names}}" 2>$null
        if ($running) {
            Write-Host "Stopping the other project's stack ($otherStack) to free shared ports..." -ForegroundColor Yellow
            Push-Location $otherStack
            docker compose down
            Pop-Location
        }
    }
}

# --- 3. Start the backend ---
Write-Host "Starting backend..." -ForegroundColor Cyan
Push-Location "$root\backend"
docker compose up -d
Pop-Location

Write-Host "Waiting for services to become healthy..." -ForegroundColor Cyan
$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 5
    Push-Location "$root\backend"
    $unhealthy = docker compose ps --format json 2>$null | ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { $_.Health -and $_.Health -ne "healthy" }
    Pop-Location
} while ($unhealthy -and (Get-Date) -lt $deadline)

if ($unhealthy) {
    Write-Host "Some services still aren't healthy after 3 minutes -- check with 'docker compose ps' in backend/." -ForegroundColor Yellow
    $unhealthy | ForEach-Object { Write-Host "  - $($_.Service): $($_.Health)" -ForegroundColor Yellow }
} else {
    Write-Host "Backend is healthy." -ForegroundColor Green
}

# --- 4. Make sure port 5173 is actually free before starting the frontend ---
# A prior run's dev server (crashed terminal, killed window, whatever) can be
# left holding the port -- Vite would then silently start on 5174/5175/...
# instead, or refuse to start. Always kill whatever's there first so this
# step can never fail because of leftover state from last time.
Write-Host "Making sure port 5173 is free..." -ForegroundColor Cyan
$portPid = (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($portPid) {
    Write-Host "Port 5173 is held by process $portPid from a previous run -- stopping it." -ForegroundColor Yellow
    Stop-Process -Id $portPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
# Also clean up any other leftover frontend dev-server processes (and their
# parent shell windows) from a previous run of this same script, even if
# they never actually managed to bind to 5173 -- e.g. two crashed instances
# sitting idle. Without this, closing/reopening the terminal window alone
# isn't enough to guarantee a clean slate.
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*IBVAP+Thermal\frontend*npm run dev*" -or
    $_.CommandLine -like "*IBVAP+Thermal\frontend\node_modules*vite*"
} | ForEach-Object {
    Write-Host "Stopping leftover frontend process $($_.ProcessId)..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# --- 5. Start the frontend in its own window ---
Write-Host "Starting frontend in a new window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8080" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "Log in with the admin credentials from backend\.env (BOOTSTRAP_ADMIN_USERNAME/PASSWORD)."
