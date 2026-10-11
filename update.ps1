# Updates a downloaded ZIP checkout while preserving .env, data, .venv and scenes.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path '.git') {
    throw 'Ce dossier utilise Git. Arrete Jarvis puis utilise git pull, sans ecraser tes changements locaux.'
}
$JarvisDownload = Join-Path $env:TEMP ('Jarvis-download-' + [guid]::NewGuid().ToString())
$JarvisBackup = Join-Path $env:TEMP ('Jarvis-source-backup-' + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $JarvisDownload, $JarvisBackup | Out-Null
$JarvisItems = @('app', 'ui', 'docs', 'tests', 'main.py', 'start.ps1', 'requirements.txt', 'requirements.lock', 'README.md')
try {
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 120 -Uri 'https://github.com/ilonasaunier05-wq/forfun/archive/refs/heads/main.zip' -OutFile (Join-Path $JarvisDownload 'source.zip')
    Expand-Archive -Path (Join-Path $JarvisDownload 'source.zip') -DestinationPath (Join-Path $JarvisDownload 'source')
    $JarvisSource = Join-Path $JarvisDownload 'source/forfun-main'
    if (-not (Test-Path (Join-Path $JarvisSource 'app/main.py'))) { throw 'Archive invalide. Aucun fichier remplace.' }
    foreach ($JarvisItem in $JarvisItems) {
        if (-not (Test-Path (Join-Path $JarvisSource $JarvisItem))) { throw "Fichier manquant : $JarvisItem. Aucun fichier remplace." }
    }
    foreach ($JarvisItem in $JarvisItems) {
        if (Test-Path $JarvisItem) { Copy-Item -Path $JarvisItem -Destination $JarvisBackup -Recurse -Force }
    }
    foreach ($JarvisItem in $JarvisItems) {
        Copy-Item -Path (Join-Path $JarvisSource $JarvisItem) -Destination $PSScriptRoot -Recurse -Force
    }
    foreach ($JarvisObsolete in @('app/intents.py', 'ui/voice.js', 'ui/JARVIS_HUD_DEMO.html')) {
        if (Test-Path $JarvisObsolete) { Remove-Item $JarvisObsolete -Force }
    }
    if (-not (Test-Path 'config.yaml')) { Copy-Item (Join-Path $JarvisSource 'config.yaml') -Destination $PSScriptRoot }
    Write-Host "Mise a jour terminee. .env, data, .venv et scenes.json conserves."
    Write-Host "Sauvegarde des anciens fichiers : $JarvisBackup"
    Write-Host 'Relance .\start.ps1 puis actualise le navigateur avec Ctrl+F5.'
} finally {
    Remove-Item -Path $JarvisDownload -Recurse -Force
}
