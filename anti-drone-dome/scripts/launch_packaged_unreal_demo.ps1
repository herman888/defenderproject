<# Starts the continuous demo with the packaged viewer (no Unreal editor needed). #>

$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$python = Join-Path $workspaceRoot 'gym-pybullet-drones\.venv\Scripts\python.exe'
$viewer = Join-Path $workspaceRoot 'unreal\builds\AegisTacticalViewer-Win64\Windows\AegisTacticalViewer.exe'
$logRoot = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\Saved\Logs'

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $viewer)) {
    throw 'Python environment or packaged viewer was not found. Build the packaged viewer first.'
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

Start-Process -FilePath $viewer -WorkingDirectory (Split-Path $viewer)
Write-Host 'Packaged local demo started.'
