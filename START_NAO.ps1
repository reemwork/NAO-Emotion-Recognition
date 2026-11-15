param(
    [string]$NaoIP = '',
    [int]$BackendPort = 8000
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$root = $PSScriptRoot
$logDir = Join-Path $root 'data\startup_logs'
$configPath = Join-Path $root 'nao_connection.json'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Info([string]$message) { Write-Host "[NAO] $message" -ForegroundColor Cyan }
function Fail([string]$message) { throw $message }

function Wait-Http([string]$url, [int]$seconds) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $seconds) {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return $true }
        } catch { }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Valid-IPv4([string]$value) {
    $parsed = $null
    return [Net.IPAddress]::TryParse($value, [ref]$parsed) -and
        $parsed.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
        $value -match '^\d{1,3}(\.\d{1,3}){3}$'
}

function Test-SshPort([string]$address) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($address, 22, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1800, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch { return $false }
    finally { $client.Close() }
}

function Detect-NaoAddress {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($NaoIP) { [void]$candidates.Add($NaoIP.Trim()) }
    if ($env:NAO_IP) { [void]$candidates.Add($env:NAO_IP.Trim()) }
    if (Test-Path -LiteralPath $configPath) {
        try {
            $saved = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($saved.nao_ip) { [void]$candidates.Add([string]$saved.nao_ip) }
        } catch { Info 'Saved IP configuration could not be read; ignoring it.' }
    }
    # Resolve a single known local hostname (mDNS when supported); NEVER scan the campus subnet.
    try {
        foreach ($addr in [Net.Dns]::GetHostAddresses('nao.local')) {
            if ($addr.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
                [void]$candidates.Add($addr.IPAddressToString)
            }
        }
    } catch { }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Valid-IPv4 $candidate)) { continue }
        Info "Checking NAO SSH on $candidate ..."
        if (Test-SshPort $candidate) { return $candidate }
    }

    Write-Host 'NAO was not found at its saved IP or nao.local.' -ForegroundColor Yellow
    Write-Host 'Check the IP shown in Choregraphe, then enter it below.'
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $answer = Read-Host 'NAO IPv4 address (blank to cancel)'
        if ([string]::IsNullOrWhiteSpace($answer)) { Fail 'Cancelled. No robot session was started.' }
        $answer = $answer.Trim()
        if (-not (Valid-IPv4 $answer)) {
            Write-Host 'Invalid IPv4 address.' -ForegroundColor Yellow
            continue
        }
        if (Test-SshPort $answer) { return $answer }
        Write-Host "SSH port 22 is not reachable at $answer." -ForegroundColor Yellow
    }
    Fail 'Could not reach NAO. Check its current IP and network connectivity.'
}

try {
    Info "Project: $root"
    $python = Join-Path $root 'venv\Scripts\python.exe'
    foreach ($required in @($python, (Join-Path $root 'backend\app.py'), (Join-Path $root 'run_session.py'))) {
        if (-not (Test-Path -LiteralPath $required)) { Fail "Required file not found: $required" }
    }
    if ($BackendPort -ne 8000) { Fail 'run_session.py currently uses port 8000; leave BackendPort=8000.' }

    # Check the robot BEFORE starting a session. This does not send any movement or recording commands.
    $selectedIP = Detect-NaoAddress
    Info "NAO SSH reachable at $selectedIP. Session checks will verify NAOqi and SSH authentication."

    $ollamaUrl = 'http://127.0.0.1:11434/api/tags'
    if (-not (Wait-Http $ollamaUrl 2)) {
        $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
        $exe = if ($command) { $command.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
        if (-not (Test-Path -LiteralPath $exe)) { Fail 'Ollama executable not found. Install Ollama first.' }
        Info 'Starting Ollama...'
        Start-Process -FilePath $exe -ArgumentList @('serve') -WorkingDirectory $root -RedirectStandardOutput (Join-Path $logDir 'ollama.out.log') -RedirectStandardError (Join-Path $logDir 'ollama.err.log') | Out-Null
    }
    if (-not (Wait-Http $ollamaUrl 45)) { Fail 'Ollama unavailable. Check data\startup_logs\ollama.err.log' }
    $tags = Invoke-RestMethod -Uri $ollamaUrl -TimeoutSec 10
    $names = @($tags.models | ForEach-Object { $_.name })
    if ('qwen2.5vl:3b' -notin $names) { Fail 'qwen2.5vl:3b is missing. Run once: ollama pull qwen2.5vl:3b' }
    Info 'Ollama / Qwen ready.'

    $backendUrl = 'http://127.0.0.1:8000/'
    if (-not (Wait-Http $backendUrl 2)) {
        Info 'Starting FastAPI...'
        Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $root -RedirectStandardOutput (Join-Path $logDir 'fastapi.out.log') -RedirectStandardError (Join-Path $logDir 'fastapi.err.log') | Out-Null
    }
    if (-not (Wait-Http $backendUrl 60)) { Fail 'FastAPI unavailable. Check data\startup_logs\fastapi.err.log' }
    Info 'FastAPI ready.'

    Info "Starting NAO session with $selectedIP ..."
    & $python (Join-Path $root 'run_session.py') --nao-ip $selectedIP
    if ($LASTEXITCODE -ne 0) { Fail "Session coordinator failed (exit $LASTEXITCODE). Verify SSH authentication, NAOqi, and model inference." }

    # Remember a successfully used robot address for the next launch.
    @{ nao_ip = $selectedIP } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    Info "Session complete. Saved IP $selectedIP for the next launch."
    exit 0
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No automatic subnet-wide scan was performed. Check current NAO IP and SSH setup.' -ForegroundColor Yellow
    exit 1
}
