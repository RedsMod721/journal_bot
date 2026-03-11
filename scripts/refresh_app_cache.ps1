param(
    [switch]$Deep
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendCmd = "Set-Location '$repoRoot'; .\.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --port 8000"
$frontCmd = @"
`$env:Path += ';' + `$env:USERPROFILE + '\.cargo\bin'
`$env:CARGO_HTTP_CHECK_REVOKE = 'false'
Set-Location '$repoRoot\rpg-life-ui'
npm run tauri:dev
"@

Write-Host "[1/5] Stopping backend listener on port 8000 (if any)..." -ForegroundColor Cyan
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    try {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
        Start-Sleep -Seconds 1
        Write-Host "Stopped PID $($conn.OwningProcess)" -ForegroundColor Yellow
    } catch {
        Write-Host "Listener PID already exited: $($conn.OwningProcess)" -ForegroundColor DarkGray
    }
} else {
    Write-Host "No process currently listening on 8000." -ForegroundColor DarkGray
}

Write-Host "[2/5] Clearing Python bytecode caches..." -ForegroundColor Cyan
Get-ChildItem -Path (Join-Path $repoRoot "src"), (Join-Path $repoRoot "app") -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[3/5] Clearing frontend Vite cache..." -ForegroundColor Cyan
$viteCache = Join-Path $repoRoot "rpg-life-ui\node_modules\.vite"
if (Test-Path $viteCache) {
    Remove-Item -Recurse -Force $viteCache
    Write-Host "Removed $viteCache" -ForegroundColor Yellow
} else {
    Write-Host "No Vite cache folder found." -ForegroundColor DarkGray
}

if ($Deep) {
    Write-Host "[3b/5] Deep clean: clearing local Qdrant cache path..." -ForegroundColor Cyan
    $qdrantLocal = Join-Path $repoRoot "data\qdrant_local"
    if (Test-Path $qdrantLocal) {
        Get-ChildItem -Path $qdrantLocal -Force -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared $qdrantLocal" -ForegroundColor Yellow
    } else {
        Write-Host "No local Qdrant cache folder found." -ForegroundColor DarkGray
    }
}

Write-Host "[4/5] Starting backend in a new PowerShell window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd | Out-Null

Write-Host "[5/5] Starting frontend in a new PowerShell window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontCmd | Out-Null

Write-Host "Done. Backend and frontend relaunch requested." -ForegroundColor Green
if ($Deep) {
    Write-Host "Deep mode was enabled (Qdrant local cache cleared)." -ForegroundColor Green
}
