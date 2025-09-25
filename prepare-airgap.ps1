[CmdletBinding()]
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [string]$BundleName = 'terminalx-airgap-bundle',
    [switch]$SkipPull,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectPath = (Resolve-Path -Path $ProjectRoot).Path
$bundleRoot = Join-Path -Path $projectPath -ChildPath $BundleName
$imagesDir = Join-Path -Path $bundleRoot -ChildPath 'images'
$configDir = Join-Path -Path $bundleRoot -ChildPath 'config'

if (Test-Path -Path $bundleRoot) {
    if ($Force) {
        Remove-Item -Path $bundleRoot -Recurse -Force
    }
    else {
        throw "Bundle directory '" + $bundleRoot + "' already exists. Use -Force to overwrite."
    }
}

New-Item -ItemType Directory -Path $imagesDir -Force | Out-Null
New-Item -ItemType Directory -Path $configDir -Force | Out-Null

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI not found. Install Docker Desktop or CLI before running this script.'
}

$images = @(
    @{ Reference = 'terminalx:1.1.3.2f' }
    @{ Reference = 'sftp-server:1.0.2.1' }
    @{ Reference = 'nginx:1.25-alpine' }
)

$manifestLines = @()
$manifestLines += 'TerminalX Air-Gap Bundle'
$manifestLines += '========================='
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$manifestLines += "Generated: $timestamp"
$manifestLines += ''
$manifestLines += 'Images:'

foreach ($image in $images) {
    $reference = $image.Reference
    Write-Host ("Processing {0}" -f $reference) -ForegroundColor Cyan

    if (-not $SkipPull) {
        Write-Host ("  docker pull {0}" -f $reference) -ForegroundColor DarkGray
        docker pull $reference | Write-Output
    }

    $safeName = ($reference -replace '[^A-Za-z0-9_.-]', '_') + '.tar'
    $tarPath = Join-Path -Path $imagesDir -ChildPath $safeName

    Write-Host ("  docker save -> {0}" -f $safeName) -ForegroundColor DarkGray
    docker save --output $tarPath $reference

    $sizeMB = '{0:N2}' -f ((Get-Item -Path $tarPath).Length / 1MB)
    $manifestLines += "  - $reference ($sizeMB MB)"
}

$manifestLines += ''
$manifestLines += 'To load on the air-gapped host:'
$manifestLines += '  1. Copy the bundle directory to the target machine.'
$manifestLines += '  2. Run .\images\load-images.ps1 (PowerShell) to import the images.'
$manifestLines += '  3. Verify with: docker images'
$manifestPath = Join-Path -Path $bundleRoot -ChildPath 'README-airgap.txt'
Set-Content -Path $manifestPath -Value $manifestLines -Encoding UTF8

$loadScript = @'
[CmdletBinding()]
param(
    [string]$ImagesPath = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker CLI not found. Install Docker before loading images.'
}

Get-ChildItem -Path $ImagesPath -Filter '*.tar' | Sort-Object Name | ForEach-Object {
    Write-Host ("Loading {0}..." -f $PSItem.Name) -ForegroundColor Cyan
    docker load --input $PSItem.FullName | Write-Output
}

Write-Host 'All images loaded successfully.' -ForegroundColor Green
'@
Set-Content -Path (Join-Path -Path $imagesDir -ChildPath 'load-images.ps1') -Value $loadScript -Encoding UTF8

$filesToCopy = @(
    'docker-compose.yml',
    'nginx.conf'
)

foreach ($item in $filesToCopy) {
    $sourcePath = Join-Path -Path $projectPath -ChildPath $item
    if (Test-Path -Path $sourcePath) {
        Copy-Item -Path $sourcePath -Destination (Join-Path -Path $configDir -ChildPath $item) -Force
    }
}

$nginxDir = Join-Path -Path $projectPath -ChildPath 'nginx'
if (Test-Path -Path $nginxDir) {
    Copy-Item -Path $nginxDir -Destination (Join-Path -Path $configDir -ChildPath 'nginx') -Recurse -Force
}

Write-Host ("Air-gap bundle created at {0}" -f $bundleRoot) -ForegroundColor Green
Write-Host 'Transfer the entire bundle to the air-gapped server and run load-images.ps1 before docker compose up.'
