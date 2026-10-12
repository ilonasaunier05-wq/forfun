param([int]$Port = 8000, [switch]$Text, [switch]$Selftest)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.11 -m venv .venv }
    if (-not (Test-Path '.venv/Scripts/python.exe') -and (Get-Command python -ErrorAction SilentlyContinue)) { python -m venv .venv }
    if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Installe Python 3.11 ou 3.12 avec Add Python to PATH, puis rouvre PowerShell.' }
    if ($LASTEXITCODE -ne 0) { throw 'Creation de .venv impossible. Installe Python 3.11 ou utilise python -m venv .venv.' }
}
$JarvisPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $JarvisPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
$JarvisArgs = @('main.py', '--port', "$Port")
if ($Text) { $JarvisArgs += '--text' }
if ($Selftest) { $JarvisArgs += '--selftest' }
& $JarvisPython @JarvisArgs
exit $LASTEXITCODE
