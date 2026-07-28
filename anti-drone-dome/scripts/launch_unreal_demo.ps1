<# Starts the local display-only pipeline: simulator -> bridge -> Unreal. #>

$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$python = Join-Path $workspaceRoot 'gym-pybullet-drones\.venv\Scripts\python.exe'
$project = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\AegisTacticalViewer.uproject'
$logRoot = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\Saved\Logs'

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $project)) {
    throw 'Python environment or canonical Unreal project was not found.'
}

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and (
        $_.CommandLine -like '*integration\unreal_bridge.py*' -or
        $_.CommandLine -like '*main.py*--demo-repeat*'
    )
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Process -FilePath $python -ArgumentList @(
    '-u', 'integration\unreal_bridge.py', '--listen', '127.0.0.1:8787',
    '--unreal', '127.0.0.1:8788', '--stats-interval', '120'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-bridge-live.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-bridge-live.error.log')

Start-Process -FilePath $python -ArgumentList @(
    'main.py', '--auto-start', '--demo-repeat', '--telemetry-udp', '127.0.0.1:8787',
    '--telemetry-record', 'missions\renderer\unreal-demo.jsonl'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'simulator-live.log') `
    -RedirectStandardError (Join-Path $logRoot 'simulator-live.error.log')

Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' `
    -ArgumentList ('"' + $project + '"') -WorkingDirectory (Split-Path $project)

Write-Host 'Demo started. When Unreal opens, press Play once.'
