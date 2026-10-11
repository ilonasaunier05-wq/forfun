param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11+ with the Windows py launcher first.' }
}
$JarvisPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $JarvisPython -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Write-Host "JARVIS: http://127.0.0.1:$Port - open in Chrome or Edge. Ctrl+C stops the server."
& $JarvisPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --no-proxy-headers
exit $LASTEXITCODE
