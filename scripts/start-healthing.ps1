# Start Health-ing uvicorn on 127.0.0.1:8000 if not already listening.
# Used by Scheduled Task: Health-ing-uvicorn

$ErrorActionPreference = 'Continue'
$ProjectRoot = 'C:\tube\Health-ing'
$PythonExe   = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDir      = Join-Path $ProjectRoot 'logs'
$LogFile     = Join-Path $LogDir 'uvicorn.log'
$HostAddr    = '127.0.0.1'
$Port        = 8000

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Write-Log([string]$Message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogFile -Value "[$stamp] $Message" -Encoding UTF8
}

function Test-PortListening {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq $HostAddr -or $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' } |
            Select-Object -First 1
        return $null -ne $conn
    } catch {
        return $false
    }
}

if (-not (Test-Path $PythonExe)) {
    Write-Log "ERROR: Python not found at $PythonExe"
    exit 1
}

if (Test-PortListening) {
    Write-Log "SKIP: already listening on ${HostAddr}:${Port}"
    exit 0
}

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
if (Test-PortListening) {
    Write-Log "OK: listening on ${HostAddr}:${Port}"
    exit 0
}

Write-Log "WARN: process started (pid=$($proc.Id)) but port $Port not yet listening"
exit 0
