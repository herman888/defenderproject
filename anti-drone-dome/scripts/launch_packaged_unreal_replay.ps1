<# Replays the newest validated Unreal tactical recording in the packaged viewer. #>

$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$python = Join-Path $workspaceRoot 'gym-pybullet-drones\.venv\Scripts\python.exe'
$viewer = Join-Path $workspaceRoot 'unreal\builds\AegisTacticalViewer-Win64-curated\Windows\AegisTacticalViewer.exe'
$logRoot = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\Saved\Logs'
$recordingRoot = Join-Path $demoRoot 'missions\renderer'

function Stop-AegisReplayHelpers {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match
            '(?i)(integration\\unreal_bridge\.py|scripts\\replay_tactical_stream\.py)'
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $viewer)) {
    throw 'Python environment or packaged viewer was not found.'
}
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$recording = Get-ChildItem -LiteralPath $recordingRoot -Filter 'unreal-demo*.jsonl' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($null -eq $recording) {
    throw 'No Unreal tactical recording exists yet. Run the live demo first.'
}

Stop-AegisReplayHelpers
Start-Process -FilePath $python -ArgumentList @(
    '-u', 'integration\unreal_bridge.py', '--listen', '127.0.0.1:8787',
    '--unreal', '127.0.0.1:8788', '--stats-interval', '120'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-replay-bridge.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-replay-bridge.error.log')

Start-Process -FilePath $viewer -WorkingDirectory (Split-Path $viewer)
Start-Sleep -Seconds 4
Start-Process -FilePath $python -ArgumentList @(
    # The recording path MUST be quoted. Passed bare, any directory containing
    # a space - "...\Side Projects\..." here - splits into separate arguments
    # and replay_tactical_stream.py dies with "unrecognized arguments" before
    # sending a single packet, leaving the viewer stuck on
    # "WAITING FOR LOCAL TELEMETRY" with no obvious cause.
    'scripts\replay_tactical_stream.py',
    "--input=`"$($recording.FullName)`"",
    # A 0.5x replay gives the range-observer camera enough time to show real
    # world-space transit and makes the engagement intelligible at a glance.
    '--udp', '127.0.0.1:8787', '--rate', '0.5',
    # One mission is only a few seconds of playback; loop so the display stays
    # live instead of going stale a moment after launch.
    '--loop', '0'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-replay.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-replay.error.log')

Write-Host "Replaying $($recording.Name) at 0.5x in the packaged viewer."
