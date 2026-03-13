param(
    [ValidateSet("web", "tauri")]
    [string]$Mode = "web",
    [int]$Port = 1420
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uiRoot = Join-Path $repoRoot "rpg-life-ui"

if (-not (Test-Path $uiRoot)) {
    throw "Frontend directory not found at $uiRoot"
}

$pathSeparator = [System.IO.Path]::PathSeparator
$homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$cargoBin = Join-Path $homeDir ".cargo/bin"
if (Test-Path $cargoBin) {
    $env:Path += "$pathSeparator$cargoBin"
}
$env:CARGO_HTTP_CHECK_REVOKE = "false"

Set-Location $uiRoot

if ($Mode -eq "web") {
    Write-Host "Starting Vite dev server on http://127.0.0.1:$Port" -ForegroundColor Cyan
    npm run dev -- --host 127.0.0.1 --port $Port --strictPort
    exit $LASTEXITCODE
}

Write-Host "Starting Tauri desktop shell (expects Vite on port 1420)." -ForegroundColor Cyan
npm run tauri:dev
exit $LASTEXITCODE
