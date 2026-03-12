param(
    [int[]]$Ports = @(8002, 1420, 5173),
    [int]$WaitSeconds = 10,
    [switch]$ForceBackendStop,
    [switch]$IncludeLegacyPorts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ListenerProcessIds {
    param(
        [int]$Port
    )

    $matched = @()

    try {
        $matched += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess
    } catch {
        $matched += netstat -ano -p tcp 2>$null |
            Select-String "LISTENING" |
            ForEach-Object {
                if ($_.Line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                    [int]$matches[1]
                }
            }
    }

    return $matched | Where-Object { $_ } | Sort-Object -Unique
}

function Test-HealthyBackendPort {
    param(
        [int]$Port
    )

    try {
        $baseUrl = "http://127.0.0.1:$Port"
        $openapi = (Invoke-WebRequest -UseBasicParsing "$baseUrl/openapi.json" -TimeoutSec 5).Content | ConvertFrom-Json
        $health = (Invoke-WebRequest -UseBasicParsing "$baseUrl/health" -TimeoutSec 5).Content | ConvertFrom-Json
    } catch {
        return $false
    }

    $paths = @($openapi.paths.PSObject.Properties.Name)
    $hasPrimaryJournal = $paths -contains "/api/journal/entries"
    $hasV1Journal = $paths -contains "/api/v1/journal/entries"
    $hasLegacyJournal = ($paths -contains "/api/api/journal/entries") -or ($paths -contains "/api/v1/api/journal/entries")
    $hasFreshHealthShape =
        ($health.PSObject.Properties.Name -contains "schema_ready") -and
        ($health.PSObject.Properties.Name -contains "schema_revision") -and
        ($health.PSObject.Properties.Name -contains "schema_head")

    return $hasPrimaryJournal -and $hasV1Journal -and -not $hasLegacyJournal -and $hasFreshHealthShape
}

$normalizedPorts = @($Ports)

if ($IncludeLegacyPorts) {
    $normalizedPorts += 8000, 8001
}

$normalizedPorts = $normalizedPorts | Sort-Object -Unique

foreach ($port in $normalizedPorts) {
    if ($port -eq 8002 -and -not $ForceBackendStop -and (Test-HealthyBackendPort -Port $port)) {
        Write-Host "Port $port already serves the expected backend. Preserving it." -ForegroundColor Green
        continue
    }

    $listenerPids = @(Get-ListenerProcessIds -Port $port)

    if ($listenerPids.Count -eq 0) {
        Write-Host "Port $port is already free." -ForegroundColor DarkGray
        continue
    }

    Write-Host "Stopping listener(s) on port ${port}: $($listenerPids -join ', ')" -ForegroundColor Cyan

    foreach ($listenerPid in $listenerPids) {
        try {
            Stop-Process -Id $listenerPid -Force -ErrorAction Stop
            Write-Host "Stopped PID $listenerPid" -ForegroundColor Yellow
        } catch {
            Write-Host "PID already exited or could not be stopped: $listenerPid" -ForegroundColor DarkGray
        }
    }

    $portCleared = $false

    for ($attempt = 1; $attempt -le $WaitSeconds; $attempt++) {
        $remaining = @(Get-ListenerProcessIds -Port $port)
        if ($remaining.Count -eq 0) {
            $portCleared = $true
            break
        }

        foreach ($remainingPid in $remaining) {
            try {
                Stop-Process -Id $remainingPid -Force -ErrorAction Stop
                Write-Host "Stopped PID $remainingPid during wait loop" -ForegroundColor Yellow
            } catch {
                Write-Host "PID already exited or could not be stopped: $remainingPid" -ForegroundColor DarkGray
            }
        }

        Start-Sleep -Seconds 1
    }

    if (-not $portCleared) {
        $remaining = @(Get-ListenerProcessIds -Port $port)
        throw "Port ${port} is still occupied after cleanup: $($remaining -join ', ')"
    }

    Write-Host "Port $port is now free." -ForegroundColor Green
}

Write-Host "Requested dev ports are clean." -ForegroundColor Green
