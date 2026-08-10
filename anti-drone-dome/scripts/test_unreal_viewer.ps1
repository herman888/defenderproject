<#
Run the frozen Unreal viewer's automation tests without opening an interactive
editor window. This is a release-quality check, not a rendering feature.
#>

[CmdletBinding()]
param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string]$ReportDirectory
)

$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$project = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\AegisTacticalViewer.uproject'
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
if (-not $ReportDirectory) {
    $ReportDirectory = Join-Path $demoRoot 'validation_reports\unreal-automation'
}
foreach ($path in @($project, $editor)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required Unreal path was not found: $path"
    }
}
New-Item -ItemType Directory -Force -Path $ReportDirectory | Out-Null
$ReportDirectory = (Resolve-Path -LiteralPath $ReportDirectory).Path

$editorArguments = @(
    $project,
    '-unattended',
    '-nop4',
    '-nosplash',
    '-NullRHI',
    '-ExecCmds=Automation RunTests Aegis.TacticalViewer;Quit',
    "-ReportExportPath=$ReportDirectory"
)
& $editor @editorArguments
if ($LASTEXITCODE -ne 0) {
    throw "Unreal automation tests failed with exit code $LASTEXITCODE"
}

$index = Join-Path $ReportDirectory 'index.json'
if (-not (Test-Path -LiteralPath $index)) {
    throw "Unreal exited without writing the automation report: $index"
}
$report = Get-Content -LiteralPath $index -Raw | ConvertFrom-Json
if ($report.failed -gt 0) {
    throw "Unreal automation report contains $($report.failed) failed test(s)"
}
Write-Host "Unreal automation tests passed. Report: $index"
