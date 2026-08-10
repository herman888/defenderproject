<#
Build a versioned, portable Win64 release of the frozen Aegis Tactical Viewer.

This script deliberately packages the existing receive-only viewer; it does not
add rendering features or any simulation-control capability.  The output is a
ZIP plus a SHA-256 manifest suitable for a private release/download channel.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$Version,

    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',

    [string]$OutputRoot,

    [switch]$ReuseExistingArchive
)

$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$project = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\AegisTacticalViewer.uproject'
$uat = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $workspaceRoot "unreal\releases\AegisTacticalViewer-Win64-$Version"
}

foreach ($path in @($project, $uat)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required Unreal path was not found: $path"
    }
}
if ((Test-Path -LiteralPath $OutputRoot) -and -not $ReuseExistingArchive) {
    throw "Release output already exists; choose a new version or use -ReuseExistingArchive: $OutputRoot"
}

if (-not $ReuseExistingArchive) {
    & $uat BuildCookRun `
        "-project=$project" `
        -noP4 -platform=Win64 -clientconfig=Shipping `
        -build -cook -stage -pak -archive "-archivedirectory=$OutputRoot"
    if ($LASTEXITCODE -ne 0) {
        throw "Unreal packaging failed with exit code $LASTEXITCODE"
    }
}

$executable = Get-ChildItem -LiteralPath $OutputRoot -Recurse -Filter 'AegisTacticalViewer*.exe' -File |
    Where-Object { $_.Length -gt 1MB } |
    Select-Object -First 1
if ($null -eq $executable) {
    throw "Packaging completed but no runtime AegisTacticalViewer.exe was found"
}

$zipPath = "$OutputRoot.zip"
Compress-Archive -LiteralPath $OutputRoot -DestinationPath $zipPath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schema = 'aegis.unreal-release.v1'
    version = $Version
    platform = 'Windows-x64'
    created_utc = [DateTime]::UtcNow.ToString('o')
    project = 'AegisTacticalViewer'
    engine_root = $EngineRoot
    executable_relative_path = $executable.FullName.Substring($OutputRoot.Length).TrimStart('\')
    zip_file = Split-Path -Leaf $zipPath
    zip_sha256 = $hash
    safety_boundary = 'receive-only local research telemetry; no command or actuation path'
}
$manifestPath = "$OutputRoot.release.json"
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Host "Release package: $zipPath"
Write-Host "SHA-256: $hash"
Write-Host "Manifest: $manifestPath"
