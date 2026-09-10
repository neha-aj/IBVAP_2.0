# Stops everything start.ps1 started: the frontend dev server and the
# backend Docker stack (Compose project "ibvap-thermal"). Safe to run even
# if some/none of it is running.

$root = $PSScriptRoot

Write-Host "Stopping frontend dev server..." -ForegroundColor Cyan
$portPid = (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($portPid) {
    Stop-Process -Id $portPid -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped process $portPid on port 5173." -ForegroundColor Green
}
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*IBVAP+Thermal\frontend*npm run dev*" -or
    $_.CommandLine -like "*IBVAP+Thermal\frontend\node_modules*vite*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopping backend..." -ForegroundColor Cyan
Push-Location "$root\backend"
docker compose down
Pop-Location

Write-Host "Done. Everything's stopped." -ForegroundColor Green
