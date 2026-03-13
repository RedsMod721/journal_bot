param(
    [int]$Port = 8002,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCandidates = @(
    (Join-Path $repoRoot ".venv/Scripts/python.exe"),
    (Join-Path $repoRoot ".venv/bin/python"),
    (Join-Path $repoRoot ".venv/bin/python3")
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    throw "Backend Python interpreter not found. Checked: $($pythonCandidates -join ', ')"
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
