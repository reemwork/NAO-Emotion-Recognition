param([string]$NaoIP = '169.254.247.199')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.\backend\app.py')) {
  Write-Host 'Copy run_session.py and START_NAO.ps1 into the GitHub project ROOT (next to backend folder).' -ForegroundColor Red
  exit 1
}
if (-not (Test-Path '.\venv\Scripts\python.exe')) {
  Write-Host 'Missing venv\Scripts\python.exe; activate/create the existing project environment first.' -ForegroundColor Red
  exit 1
}
$python = (Resolve-Path '.\venv\Scripts\python.exe').Path
Write-Host 'Starting FastAPI in a separate PowerShell window...'
$cmd = "Set-Location '$($PWD.Path)'; & '$python' -m uvicorn backend.app:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList '-NoExit','-Command',$cmd
Write-Host 'Checking services and starting coordinated NAO session...'
& $python .\run_session.py --nao-ip $NaoIP
if ($LASTEXITCODE -ne 0) { Write-Host 'Check the error above. No NAO session was verified end-to-end.' -ForegroundColor Yellow }
