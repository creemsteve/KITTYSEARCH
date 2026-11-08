param(
    [string]$Python = "python",
    [string]$Ref = "master"
)

$ErrorActionPreference = 'Stop'
$DataRoot = if ($env:KITTYSEARCH_HOME) { $env:KITTYSEARCH_HOME } else { Join-Path $PSScriptRoot 'kittysearch-data' }
$Root = Join-Path $DataRoot 'searxng-windows'
$Source = Join-Path $Root 'source'
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Archive = Join-Path $Root 'searxng-source.zip'
$Settings = Join-Path $DataRoot 'searxng-settings.yml'
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if (-not $PythonCommand) { throw "Python was not found: $Python. Install Python 3.11 or 3.12 x64 and rerun this script." }
$PythonExe = $PythonCommand.Source
$Version = & $PythonExe -c 'import struct,sys; print(sys.version_info.major,sys.version_info.minor,struct.calcsize(chr(80))*8)'
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^3 (11|12) 64$') { throw "SearXNG's Windows setup requires 64-bit Python 3.11 or 3.12. Found: $Version" }

New-Item -ItemType Directory -Force -Path $Root, $DataRoot | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $Source 'searx\webapp.py'))) {
    $Staging = Join-Path $Root ('source-staging-' + [guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $Staging | Out-Null
        $Uri = "https://github.com/searxng/searxng/archive/refs/heads/$Ref.zip"
        Write-Host "Downloading SearXNG source ($Ref)..."
        Invoke-WebRequest -Uri $Uri -OutFile $Archive -UseBasicParsing
        & $PythonExe (Join-Path $PSScriptRoot 'extract-searxng-source.py') $Archive $Staging
        if ($LASTEXITCODE -ne 0) { throw 'Could not safely extract the SearXNG source archive.' }
        if (Test-Path -LiteralPath $Source) {
            $Backup = Join-Path $Root ('source-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
            Move-Item -LiteralPath $Source -Destination $Backup
        }
        Move-Item -LiteralPath $Staging -Destination $Source
    } finally {
        if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExe -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the SearXNG virtual environment.' }
}
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip build tools.' }
Push-Location $Source
try {
    & $VenvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install SearXNG requirements.' }
    & $VenvPython -m pip install --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { throw 'Could not install SearXNG into its virtual environment.' }
} finally { Pop-Location }

& $PythonExe (Join-Path $PSScriptRoot 'patch-searxng-windows.py') $Source
if ($LASTEXITCODE -ne 0) { throw 'Could not apply the native Windows compatibility patch.' }

if (-not (Test-Path -LiteralPath $Settings)) {
    $Secret = & $VenvPython -c 'import secrets; print(secrets.token_urlsafe(48))'
    if ($LASTEXITCODE -ne 0 -or -not $Secret) { throw 'Could not generate the SearXNG secret key.' }
    @"
use_default_settings: true
server:
  secret_key: '$($Secret.Trim())'
  bind_address: 127.0.0.1
  port: 8080
  limiter: false
search:
  formats:
    - html
    - json
"@ | Set-Content -LiteralPath $Settings -Encoding UTF8
}
Write-Host "Native SearXNG setup is ready. In KittySearch select native Windows mode and use http://127.0.0.1:8080."
Write-Host "Logs will be written under: $DataRoot"
