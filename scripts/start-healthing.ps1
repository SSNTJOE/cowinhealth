# Start Health-ing uvicorn on 0.0.0.0:8000 so phones on LAN can reach /api/captcha.
# Used by Scheduled Task: Health-ing-uvicorn
# Binding only 127.0.0.1 makes App captcha show timeout / connection refused.

$ErrorActionPreference = 'Continue'
$ProjectRoot = 'C:\tube\Health-ing'
$PythonExe   = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDir      = Join-Path $ProjectRoot 'logs'
$LogFile     = Join-Path $LogDir 'uvicorn.log'
$HostAddr    = '0.0.0.0'
$Port        = 8000

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Write-Log([string]$Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogFile -Value "[$stamp] $Message" -Encoding UTF8
}

function Get-Listeners {
    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return @()
    }
}

function Test-LanReady {
    $listeners = Get-Listeners
    foreach ($conn in $listeners) {
        if ($conn.LocalAddress -eq '0.0.0.0' -or $conn.LocalAddress -eq '::') {
            return $true
        }
    }
    return $false
}

function Stop-PortListeners {
    $listeners = Get-Listeners
    $ownerIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
    foreach ($ownerId in $ownerIds) {
        try {
            Write-Log "STOP: killing pid=$ownerId (was bound on :$Port, not LAN-ready)"
            Stop-Process -Id $ownerId -Force -ErrorAction Stop
        } catch {
            Write-Log "WARN: could not stop pid=$ownerId : $($_.Exception.Message)"
        }
    }
    if ($ownerIds.Count -gt 0) {
        Start-Sleep -Seconds 1
    }
}

if (-not (Test-Path $PythonExe)) {
    Write-Log "ERROR: Python not found at $PythonExe"
    exit 1
}

if (Test-LanReady) {
    Write-Log "SKIP: already listening on 0.0.0.0:${Port} (LAN-ready)"
    exit 0
}

# Loopback-only uvicorn blocks phone captcha; replace it.
Stop-PortListeners

Write-Log "START: launching uvicorn on ${HostAddr}:${Port}"
Set-Location $ProjectRoot

$stdoutLog = Join-Path $LogDir 'uvicorn.out.log'
$stderrLog = Join-Path $LogDir 'uvicorn.err.log'

$proc = Start-Process -FilePath $PythonExe `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $HostAddr, '--port', "$Port") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

if ($null -eq $proc) {
    Write-Log 'ERROR: Start-Process returned null'
    exit 1
}

Write-Log "STARTED: pid=$($proc.Id)"

# Brief wait so caller/task can see a listen state when possible
Start-Sleep -Seconds 2
if (Test-LanReady) {
    Write-Log "OK: listening on ${HostAddr}:${Port}"
    exit 0
}

Write-Log "WARN: process started (pid=$($proc.Id)) but port $Port not yet LAN-ready"
exit 0
