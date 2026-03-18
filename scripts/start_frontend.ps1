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

function Stop-PortProcess {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TargetPort
    )

    $pids = @()

    try {
        if (Get-Command lsof -ErrorAction SilentlyContinue) {
            $rawPids = & lsof -ti TCP:$TargetPort -sTCP:LISTEN 2>$null
            if ($rawPids) {
                $pids = $rawPids | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ } | Select-Object -Unique
            }
        }
    }
    catch {
        Write-Warning "Failed to inspect port $TargetPort with lsof: $($_.Exception.Message)"
    }

    $pids = @($pids)
    if ($pids.Count -eq 0) {
        return
    }

    foreach ($pidValue in $pids) {
        try {
            $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "Stopping process '$($process.ProcessName)' (PID $pidValue) on port $TargetPort" -ForegroundColor Yellow
            }
            else {
                Write-Host "Stopping PID $pidValue on port $TargetPort" -ForegroundColor Yellow
            }
            Stop-Process -Id ([int]$pidValue) -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Unable to stop PID $pidValue on port ${TargetPort}: $($_.Exception.Message)"
        }
    }
}

Stop-PortProcess -TargetPort $Port

if ($Mode -eq "web") {
    Write-Host "Starting Vite dev server on http://127.0.0.1:$Port" -ForegroundColor Cyan
    npm run dev -- --host 127.0.0.1 --port $Port --strictPort
    exit $LASTEXITCODE
}

Write-Host "Starting Tauri desktop shell (expects Vite on port 1420)." -ForegroundColor Cyan
npm run tauri:dev
exit $LASTEXITCODE
