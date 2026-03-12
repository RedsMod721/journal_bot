param(
    [int]$Port = 8002,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Backend Python interpreter not found at $python"
}

Set-Location $repoRoot

$args = @(
    "-m",
    "uvicorn",
    "src.api.main:app",
    "--app-dir",
    $repoRoot,
    "--host",
    "127.0.0.1",
    "--port",
    "$Port"
)

if (-not $NoReload) {
    $args += "--reload"
}

Write-Host "Starting backend on http://127.0.0.1:$Port" -ForegroundColor Cyan
& $python @args
