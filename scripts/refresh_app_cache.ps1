param(
    [switch]$Deep,
    [int]$BackendPort = 8002,
    [ValidateSet("web", "tauri")]
    [string]$FrontendMode = "web",
    [int]$FrontendPort = 1420,
    [switch]$IncludeLegacyPorts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendScript = Join-Path $repoRoot "scripts\start_frontend.ps1"
$stopPortsScript = Join-Path $repoRoot "scripts\stop_dev_ports.ps1"
$backendArgs = @(
    "-m",
    "uvicorn",
    "src.api.main:app",
    "--app-dir",
    $repoRoot,
    "--host",
    "127.0.0.1",
    "--port",
    "$BackendPort",
    "--reload"
)
$backendLogDir = Join-Path $repoRoot "logs"
$backendStdout = Join-Path $backendLogDir "backend_${BackendPort}_stdout.log"
$backendStderr = Join-Path $backendLogDir "backend_${BackendPort}_stderr.log"

function Get-PortListenerProcessIds {
    param(
        [int]$Port
    )

    $matched = @()

    try {
        $matched += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess
    } catch {
        try {
            $matched += netstat -ano -p tcp 2>$null |
                Select-String "LISTENING" |
                ForEach-Object {
                    if ($_.Line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                        [int]$matches[1]
                    }
                }
        } catch {
            Write-Host "Could not inspect listeners on port ${Port}: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    return $matched | Where-Object { $_ } | Sort-Object -Unique
}

function Get-BackendProcessIds {
    $matched = @()

    try {
        $matched += Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -like '*uvicorn*' -and
                $_.CommandLine -like '*src.api.main:app*' -and
                $_.CommandLine -like "*$BackendPort*"
            } |
            Select-Object -ExpandProperty ProcessId
    } catch {
        Write-Host "Could not inspect Win32_Process command lines: $($_.Exception.Message)" -ForegroundColor DarkGray
    }

    $matched += Get-PortListenerProcessIds -Port $BackendPort

    return $matched | Where-Object { $_ } | Sort-Object -Unique
}

function Wait-ForPortToClear {
    param(
        [int]$Port,
        [int]$MaxAttempts = 10
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $remaining = @(Get-PortListenerProcessIds -Port $Port)
        if ($remaining.Count -eq 0) {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Test-BackendFreshness {
    param(
        [string]$BaseUrl = "",
        [int]$MaxAttempts = 20
    )

    if (-not $BaseUrl) {
        $BaseUrl = "http://127.0.0.1:$BackendPort"
    }

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Start-Sleep -Seconds 1

        try {
            $openapi = (Invoke-WebRequest -UseBasicParsing "$BaseUrl/openapi.json").Content | ConvertFrom-Json
            $health = (Invoke-WebRequest -UseBasicParsing "$BaseUrl/health").Content | ConvertFrom-Json
        } catch {
            if ($attempt -eq $MaxAttempts) {
                Write-Host "Backend freshness check failed: $($_.Exception.Message)" -ForegroundColor Red
                return $false
            }
            continue
        }

        $paths = @($openapi.paths.PSObject.Properties.Name)
        $hasPrimaryJournal = $paths -contains "/api/journal/entries"
        $hasV1Journal = $paths -contains "/api/v1/journal/entries"
        $hasLegacyJournal = ($paths -contains "/api/api/journal/entries") -or ($paths -contains "/api/v1/api/journal/entries")
        $hasFreshHealthShape =
            ($health.PSObject.Properties.Name -contains "schema_ready") -and
            ($health.PSObject.Properties.Name -contains "schema_revision") -and
            ($health.PSObject.Properties.Name -contains "schema_head")

        if ($hasPrimaryJournal -and $hasV1Journal -and -not $hasLegacyJournal -and $hasFreshHealthShape) {
            Write-Host "Backend freshness check passed on attempt $attempt." -ForegroundColor Green
            Write-Host "Verified routes: /api/journal/entries and /api/v1/journal/entries" -ForegroundColor Green
            return $true
        }

        if ($attempt -eq $MaxAttempts) {
            Write-Host "Backend freshness check timed out." -ForegroundColor Red
            Write-Host "hasPrimaryJournal=$hasPrimaryJournal hasV1Journal=$hasV1Journal hasLegacyJournal=$hasLegacyJournal hasFreshHealthShape=$hasFreshHealthShape" -ForegroundColor Yellow
            return $false
        }
    }

    return $false
}

if ($IncludeLegacyPorts) {
    Write-Host "[0/6] Cleaning legacy dev ports before refresh..." -ForegroundColor Cyan
    & $stopPortsScript -Ports @($BackendPort, $FrontendPort, 5173) -IncludeLegacyPorts
}

Write-Host "[1/6] Checking live backend freshness on port $BackendPort..." -ForegroundColor Cyan
$backendBaseUrl = "http://127.0.0.1:$BackendPort"
$backendAlreadyFresh = Test-BackendFreshness -BaseUrl $backendBaseUrl -MaxAttempts 1

if (-not $backendAlreadyFresh) {
    Write-Host "[2/6] Stopping backend processes for src.api.main on port $BackendPort (if any)..." -ForegroundColor Cyan
    $backendProcessIds = Get-BackendProcessIds
    if ($backendProcessIds.Count -gt 0) {
        foreach ($backendPid in $backendProcessIds) {
            try {
                Stop-Process -Id $backendPid -Force -ErrorAction Stop
                Write-Host "Stopped PID $backendPid" -ForegroundColor Yellow
            } catch {
                Write-Host "PID already exited or could not be stopped: $backendPid" -ForegroundColor DarkGray
            }
        }
        Start-Sleep -Seconds 2
    } else {
        Write-Host "No matching backend process found." -ForegroundColor DarkGray
    }

    $remainingListeners = @(Get-PortListenerProcessIds -Port $BackendPort)
    if ($remainingListeners.Count -gt 0) {
        Write-Host "Port $BackendPort still has listener(s): $($remainingListeners -join ', ')" -ForegroundColor Red
        if (-not (Wait-ForPortToClear -Port $BackendPort)) {
            throw "Port $BackendPort is still occupied after restart cleanup. Refusing to start another backend."
        }
    }
} else {
    Write-Host "Backend already fresh on port $BackendPort. Skipping restart." -ForegroundColor Green
}

Write-Host "[3/6] Clearing Python bytecode caches..." -ForegroundColor Cyan
Get-ChildItem -Path (Join-Path $repoRoot "src"), (Join-Path $repoRoot "app") -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[4/6] Clearing frontend Vite cache..." -ForegroundColor Cyan
$viteCache = Join-Path $repoRoot "rpg-life-ui\node_modules\.vite"
if (Test-Path $viteCache) {
    Remove-Item -Recurse -Force $viteCache
    Write-Host "Removed $viteCache" -ForegroundColor Yellow
} else {
    Write-Host "No Vite cache folder found." -ForegroundColor DarkGray
}

if ($Deep) {
    Write-Host "[4b/6] Deep clean: clearing local Qdrant cache path..." -ForegroundColor Cyan
    $qdrantLocal = Join-Path $repoRoot "data\qdrant_local"
    if (Test-Path $qdrantLocal) {
        Get-ChildItem -Path $qdrantLocal -Force -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared $qdrantLocal" -ForegroundColor Yellow
    } else {
        Write-Host "No local Qdrant cache folder found." -ForegroundColor DarkGray
    }
}

if (-not $backendAlreadyFresh) {
    Write-Host "[5/6] Starting backend directly from the repo virtualenv..." -ForegroundColor Cyan
    if (-not (Test-Path $backendLogDir)) {
        New-Item -Path $backendLogDir -ItemType Directory -Force | Out-Null
    }
    Remove-Item -Path $backendStdout, $backendStderr -Force -ErrorAction SilentlyContinue
    $backendProcess = Start-Process `
        -FilePath $backendPython `
        -ArgumentList $backendArgs `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $backendStdout `
        -RedirectStandardError $backendStderr `
        -PassThru
    Write-Host "Started backend PID $($backendProcess.Id)" -ForegroundColor Yellow

    Write-Host "[5b/6] Verifying live backend routes and health shape..." -ForegroundColor Cyan
    $freshBackend = Test-BackendFreshness -BaseUrl $backendBaseUrl
    if (-not $freshBackend) {
        Write-Host "Backend restart completed, but the runtime still looks stale. Check for duplicate uvicorn sessions." -ForegroundColor Red
    }
} else {
    Write-Host "[5/6] Verified existing backend routes and health shape." -ForegroundColor Green
}

Write-Host "[6/6] Starting frontend in a new PowerShell window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $frontendScript, "-Mode", $FrontendMode, "-Port", "$FrontendPort" | Out-Null

Write-Host "Done. Backend and frontend relaunch requested." -ForegroundColor Green
if ($Deep) {
    Write-Host "Deep mode was enabled (Qdrant local cache cleared)." -ForegroundColor Green
}
