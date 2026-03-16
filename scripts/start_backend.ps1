param(
    [int]$Port = 8002,
    [switch]$NoReload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# -- Load .env into the current process environment --------------------------
$envFile = Join-Path $repoRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
            }
        }
    }
    Write-Host ".env loaded from $envFile" -ForegroundColor DarkGray
}

# -- Ensure Qdrant is running ------------------------------------------------
$qdrantContainer = "qdrant_dev"
$qdrantImage     = "qdrant/qdrant"
$qdrantStorage   = Join-Path $repoRoot "data/qdrant_local"

$dockerAvailable = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
if (-not $dockerAvailable) {
    Write-Warning "docker not found on PATH -- Qdrant will not be started. RAG and semantic search will be unavailable."
} else {
    $running = docker inspect --format "{{.State.Running}}" $qdrantContainer 2>$null
    if ($running -eq "true") {
        Write-Host "Qdrant container already running." -ForegroundColor DarkGray
    } else {
        $exists = docker inspect --format "{{.Id}}" $qdrantContainer 2>$null
        if ($exists) {
            Write-Host "Removing stopped Qdrant container..." -ForegroundColor DarkGray
            docker rm $qdrantContainer | Out-Null
        }
        Write-Host "Starting Qdrant (storage: $qdrantStorage)..." -ForegroundColor Cyan
        docker run -d `
            --name $qdrantContainer `
            -p 6333:6333 `
            -p 6334:6334 `
            -v "${qdrantStorage}:/qdrant/storage" `
            $qdrantImage | Out-Null
        $ready = $false
        for ($i = 1; $i -le 15; $i++) {
            Start-Sleep -Seconds 1
            try {
                $resp = Invoke-WebRequest -Uri "http://localhost:6333/healthz" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($resp.StatusCode -eq 200) { $ready = $true; break }
            } catch {}
        }
        if ($ready) {
            Write-Host "Qdrant ready on localhost:6333" -ForegroundColor Green
        } else {
            Write-Warning "Qdrant did not become healthy within 15 s -- proceeding anyway."
        }
    }
}

# -- Locate Python interpreter ------------------------------------------------
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
