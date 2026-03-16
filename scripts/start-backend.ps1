<#
.SYNOPSIS
    Start the RPG Life Tracker backend on a chosen port.

.DESCRIPTION
    - Stops tracked/backend uvicorn process trees for the target port
    - Launches the backend detached with bounded cleanup/startup timeouts
    - Writes stdout/stderr logs plus a PID metadata file in logs/
    - Returns after readiness by default; use -Wait to block on the process

.EXAMPLE
    PS> .\scripts\start-backend.ps1

.EXAMPLE
    PS> .\scripts\start-backend.ps1 -Port 8003 -NoReload
#>

param(
    [int]$Port = 8002,
    [switch]$NoReload,
    [switch]$Wait,
    [int]$PortClearTimeoutSec = 20,
    [int]$StartupTimeoutSec = 15
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$logsDir = Join-Path $repoRoot "logs"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$stdoutLog = Join-Path $logsDir ("backend_{0}_stdout.log" -f $Port)
$stderrLog = Join-Path $logsDir ("backend_{0}_stderr.log" -f $Port)
$pidFile = Join-Path $logsDir ("backend_{0}.pid.json" -f $Port)

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

function Get-LiveProcessIds {
    param([int[]]$ProcessIds)

    if (-not $ProcessIds -or $ProcessIds.Count -eq 0) {
        return @()
    }

    $live = @()
    foreach ($candidateId in ($ProcessIds | Sort-Object -Unique)) {
        if (-not $candidateId) {
            continue
        }

        if (Get-Process -Id $candidateId -ErrorAction SilentlyContinue) {
            $live += $candidateId
        }
    }

    return @($live | Sort-Object -Unique)
}

function Read-TrackedBackendProcessIds {
    param([string]$PidMetadataPath)

    if (-not (Test-Path $PidMetadataPath)) {
        return @()
    }

    try {
        $raw = Get-Content $PidMetadataPath -Raw | ConvertFrom-Json
        $tracked = @()
        if ($raw.pid) {
            $tracked += [int]$raw.pid
        }
        if ($raw.launcher_pid) {
            $tracked += [int]$raw.launcher_pid
        }
        return Get-LiveProcessIds -ProcessIds $tracked
    } catch {
        Write-Host "Ignoring unreadable PID file $PidMetadataPath." -ForegroundColor DarkYellow
        return @()
    }
}

function Get-NetstatListenerProcessIds {
    param([int]$TargetPort)

    $listenerIds = @()
    try {
        $lines = cmd /c "netstat -ano -p tcp" 2>$null
        foreach ($line in $lines) {
            if ($line -match "^\s*TCP\s+\S+:$TargetPort\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                $listenerIds += [int]$Matches[1]
            }
        }
    } catch {
        return @()
    }

    return Get-LiveProcessIds -ProcessIds $listenerIds
}

function Get-BackendProcessIds {
    param([int]$TargetPort, [string]$PidMetadataPath)

    $processIds = @()
    $processIds += Read-TrackedBackendProcessIds -PidMetadataPath $PidMetadataPath

    try {
        $processIds += @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object {
                    $cmd = $_.CommandLine
                    if (-not $cmd) {
                        return $false
                    }

                    $looksLikeBackend = (
                        $cmd -like "*uvicorn*" -and
                        $cmd -like "*src.api.main:app*" -and
                        $cmd -match "(^| )--port $TargetPort( |$)"
                    )

                    $looksLikeLauncher = (
                        ($_.Name -eq "powershell.exe" -or $_.Name -eq "pwsh.exe") -and
                        $cmd -like "*start-backend.ps1*" -and
                        $cmd -match "(^| )-Port $TargetPort( |$)"
                    )

                    return ($looksLikeBackend -or $looksLikeLauncher)
                } |
                Select-Object -ExpandProperty ProcessId
        )
    } catch {
        Write-Host "Could not inspect process command lines; using tracked PID and netstat cleanup only." -ForegroundColor DarkYellow
    }

    $processIds += Get-NetstatListenerProcessIds -TargetPort $TargetPort
    return Get-LiveProcessIds -ProcessIds @($processIds | Where-Object { $_ } | Sort-Object -Unique)
}

function Stop-BackendProcessTree {
    param([int]$ProcessId)

    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
        return $true
    }

    try {
        cmd /c "taskkill /PID $ProcessId /T /F" | Out-Null
    } catch {
        try {
            Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        } catch {
        }
    }

    Start-Sleep -Milliseconds 500
    return -not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Clear-BackendProcesses {
    param(
        [int]$TargetPort,
        [string]$PidMetadataPath,
        [int]$TimeoutSec
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    do {
        $backendPids = Get-BackendProcessIds -TargetPort $TargetPort -PidMetadataPath $PidMetadataPath
        if (-not $backendPids -or $backendPids.Count -eq 0) {
            if (Test-Path $PidMetadataPath) {
                Remove-Item $PidMetadataPath -Force -ErrorAction SilentlyContinue
            }
            return
        }

        Write-Host ("Stopping backend PID(s): {0}" -f ($backendPids -join ", ")) -ForegroundColor Yellow
        foreach ($backendPid in $backendPids) {
            $stopped = Stop-BackendProcessTree -ProcessId $backendPid
            if (-not $stopped) {
                Write-Host ("PID {0} is still alive after stop attempt." -f $backendPid) -ForegroundColor DarkYellow
            }
        }
    } while ((Get-Date) -lt $deadline)

    $remaining = Get-BackendProcessIds -TargetPort $TargetPort -PidMetadataPath $PidMetadataPath
    if ($remaining.Count -gt 0) {
        throw ("Timed out clearing backend processes for port {0}: {1}" -f $TargetPort, ($remaining -join ", "))
    }
}

function Wait-ForBackendReady {
    param(
        [int]$TargetPort,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSec
    )

    $uri = "http://127.0.0.1:$TargetPort/openapi.json"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    do {
        if ($Process.HasExited) {
            return $false
        }

        try {
            $response = Invoke-WebRequest -UseBasicParsing $uri -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $false
}

if (-not (Test-Path $pythonExe)) {
    throw "Python interpreter not found at $pythonExe"
}

Write-Host ("Checking for stale backend processes on port {0}..." -f $Port) -ForegroundColor Yellow
Clear-BackendProcesses -TargetPort $Port -PidMetadataPath $pidFile -TimeoutSec $PortClearTimeoutSec

if (Test-Path Env:DATABASE_URL) {
    Write-Host "Clearing DATABASE_URL" -ForegroundColor Gray
    Remove-Item Env:DATABASE_URL
}

$args = @(
    "-m", "uvicorn",
    "src.api.main:app",
    "--app-dir", $repoRoot,
    "--host", "127.0.0.1",
    "--port", $Port
)

if (-not $NoReload) {
    $args += "--reload"
}

Write-Host ("Starting backend on http://127.0.0.1:{0}" -f $Port) -ForegroundColor Cyan
Write-Host ("Interpreter: {0}" -f (Resolve-Path $pythonExe)) -ForegroundColor Gray
Write-Host ("Stdout log: {0}" -f $stdoutLog) -ForegroundColor Gray
Write-Host ("Stderr log: {0}" -f $stderrLog) -ForegroundColor Gray

$backendProc = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $args `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

@{
    pid = $backendProc.Id
    launcher_pid = $PID
    port = $Port
    reload = (-not $NoReload)
    launched_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    interpreter = $pythonExe
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
} | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

Write-Host ("Started backend PID: {0}" -f $backendProc.Id) -ForegroundColor Gray

$ready = Wait-ForBackendReady -TargetPort $Port -Process $backendProc -TimeoutSec $StartupTimeoutSec
if (-not $ready) {
    if (-not $backendProc.HasExited) {
        try {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction Stop
        } catch {
        }
    }

    Write-Host "Backend did not become ready before timeout." -ForegroundColor Red
    if (Test-Path $stderrLog) {
        Write-Host "`nLast stderr lines:" -ForegroundColor DarkYellow
        Get-Content $stderrLog -Tail 40
    }
    if (Test-Path $stdoutLog) {
        Write-Host "`nLast stdout lines:" -ForegroundColor DarkYellow
        Get-Content $stdoutLog -Tail 40
    }

    throw ("Backend startup timed out after {0}s on port {1}" -f $StartupTimeoutSec, $Port)
}

Write-Host ("Backend is ready on port {0}." -f $Port) -ForegroundColor Green

if ($Wait) {
    Write-Host "Waiting on backend process. Press Ctrl+C to stop." -ForegroundColor Gray
    Wait-Process -Id $backendProc.Id
}
