<# Launch the packaged viewer with a slow, deterministic swarm-planning replay. #>

param(
    [string]$Scenario = 'saturation_6v4'
)

$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$python = Join-Path $workspaceRoot 'gym-pybullet-drones\.venv\Scripts\python.exe'
$viewer = Join-Path $workspaceRoot 'unreal\builds\AegisTacticalViewer-Win64-curated\Windows\AegisTacticalViewer.exe'
$logRoot = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\Saved\Logs'
$recording = Join-Path $demoRoot "missions\renderer\swarm-$Scenario.jsonl"

function Stop-AegisReplayHelpers {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match
            '(?i)(integration\\unreal_bridge\.py|scripts\\replay_(tactical|swarm)_stream\.py)'
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $viewer)) {
    throw 'Python environment or packaged viewer was not found.'
}

# This produces native aegis.swarm-coordination.v1 packets. The adapter focuses
# the viewer on one assigned pair; it is labelled a planning simulation and is
# not a multi-target sensor-performance claim.
& $python 'scripts\record_swarm_replay.py' '--scenario' $Scenario '--output' $recording
if ($LASTEXITCODE -ne 0) {
    throw 'Swarm recording failed.'
}

Stop-AegisReplayHelpers
Start-Process -FilePath $python -ArgumentList @(
    '-u', 'integration\unreal_bridge.py', '--listen', '127.0.0.1:8787',
    '--unreal', '127.0.0.1:8788', '--stats-interval', '120'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-swarm-bridge.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-swarm-bridge.error.log')

Start-Process -FilePath $viewer -WorkingDirectory (Split-Path $viewer)
Start-Sleep -Seconds 4
Start-Process -FilePath $python -ArgumentList @(
    'scripts\replay_swarm_stream.py', "--input=`"$recording`"",
    '--udp', '127.0.0.1:8787', '--rate', '0.5', '--loop', '0'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-swarm-replay.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-swarm-replay.error.log')

Write-Host "Replaying $Scenario at 0.5x (planning simulation focus view)."
