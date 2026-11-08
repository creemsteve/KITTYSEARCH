param(
    [string]$Distro = 'Ubuntu'
)

$ErrorActionPreference = 'Stop'
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    throw 'WSL was not found. Install it with: wsl --install -d Ubuntu. Restart Windows if prompted, then run this script again.'
}

$installed = wsl.exe --list --quiet 2>$null | ForEach-Object { ($_ -replace "`0", '').Trim() } | Where-Object { $_ }
if ($LASTEXITCODE -ne 0 -or $installed -notcontains $Distro) {
    throw "The WSL distribution '$Distro' is not installed. Install it with: wsl --install -d $Distro. Complete its first-run setup, then run this script again."
}

$wslScript = (wsl.exe -d $Distro -- wslpath -a "$PSScriptRoot\setup-searxng-wsl.sh" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslScript) {
    throw "Could not translate the setup script path into WSL for '$Distro'."
}

Write-Host "Installing SearXNG in WSL distribution '$Distro'. This installs Linux packages and Python dependencies; it does not install Docker."
wsl.exe -d $Distro -- bash $wslScript
if ($LASTEXITCODE -ne 0) {
    throw 'SearXNG setup failed inside WSL. Review the error above and rerun this script after resolving it.'
}

Write-Host "Setup complete. In KittySearch, choose the WSL2 mode and keep the SearXNG URL at http://127.0.0.1:8080."
Write-Host "If you selected a non-default distro, set KITTYSEARCH_WSL_DISTRO=$Distro before launching KittySearch."
