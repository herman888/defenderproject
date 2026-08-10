<# Starts the continuous demo with the packaged viewer (no Unreal editor needed). #>

$demoRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $demoRoot
$python = Join-Path $workspaceRoot 'gym-pybullet-drones\.venv\Scripts\python.exe'
$viewer = Join-Path $workspaceRoot 'unreal\builds\AegisTacticalViewer-Win64-curated\Windows\AegisTacticalViewer.exe'
$logRoot = Join-Path $workspaceRoot 'unreal\AegisTacticalViewer\Saved\Logs'

function Stop-AegisDemoProcessTree([int]$ProcessId) {
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId } |
        ForEach-Object { Stop-AegisDemoProcessTree $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-AegisDemoHelpers {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match '(?i)(integration\\unreal_bridge\.py|main\.py.*--(auto-start|demo-repeat|external-viewer-only|swarm))'
    } | ForEach-Object { Stop-AegisDemoProcessTree $_.ProcessId }
}

if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $viewer)) {
    throw 'Python environment or packaged viewer was not found. Build the packaged viewer first.'
}
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

Stop-AegisDemoHelpers
Start-Sleep -Milliseconds 500

Start-Process -FilePath $python -ArgumentList @(
    '-u', 'integration\unreal_bridge.py', '--listen', '127.0.0.1:8787',
    '--unreal', '127.0.0.1:8788', '--stats-interval', '120'
) -WorkingDirectory $demoRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logRoot 'unreal-bridge-live.log') `
    -RedirectStandardError (Join-Path $logRoot 'unreal-bridge-live.error.log')

$simProcess = Start-Process -FilePath $python -ArgumentList @(
    'main.py', '--auto-start', '--auto-start-speed', '4', '--demo-repeat',
    '--external-viewer-only', '--sim-control-udp', '127.0.0.1:8789', '--telemetry-udp', '127.0.0.1:8787',
    '--telemetry-record', 'missions\renderer\unreal-demo.jsonl'
) -WorkingDirectory $demoRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logRoot 'simulator-live.log') `
    -RedirectStandardError (Join-Path $logRoot 'simulator-live.error.log')

# Contention management between the viewer and the simulator.
#
# These two do not share a machine gracefully. Measured on a 4-core/8-thread
# i7-9750H, counting completed missions in ~110 s:
#
#   simulator alone .................................. 6 missions
#   + viewer at full quality ......................... 0
#   + viewer with Lumen/fog off, 720p, 30 fps ........ 1
#   + also CPU-affinity separated .................... 2
#
# So the mitigations below recover roughly a third of standalone throughput.
# They are worth applying, but the honest answer on this class of hardware is to
# use launch_packaged_unreal_replay.ps1 instead: record with the simulator alone
# (full speed, correct behaviour) and replay the JSONL into the viewer, which
# removes the contention entirely.
#
# ExecCmds syntax matters. It must be ONE quoted token with COMMA separators.
# An unquoted or pipe-separated form is silently mis-parsed - UE treats the
# fragment after the first space as a map name and tries to resolve it as a
# network host, and the console variables are never applied.
$viewerArgs = @(
    '-ResX=1280', '-ResY=720', '-WindowMode=Windowed',
    '-ExecCmds="r.Lumen.DiffuseIndirect.Allow 0,r.Shadow.Virtual.Enable 0,r.VolumetricFog 0,t.MaxFPS 30"'
)
$viewerProcess = Start-Process -FilePath $viewer -WorkingDirectory (Split-Path $viewer) `
    -ArgumentList $viewerArgs -PassThru

# Split the logical cores: the viewer gets the low half, the simulator the high
# half, so UE's task graph cannot saturate every core and stall Python.
$coreCount = [Environment]::ProcessorCount
if ($coreCount -ge 4) {
    $half = [math]::Floor($coreCount / 2)
    $lowMask = [IntPtr]((1 -shl $half) - 1)
    $highMask = [IntPtr](((1 -shl $coreCount) - 1) -band -bnot ((1 -shl $half) - 1))
    try {
        $viewerProcess.ProcessorAffinity = $lowMask
        $viewerProcess.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::Idle
        $simProcess.ProcessorAffinity = $highMask
        $simProcess.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::High
        Write-Host "Split $coreCount logical cores: viewer 0-$($half-1), simulator $half-$($coreCount-1)."
    } catch {
        Write-Host 'Could not set affinity/priority; continuing unpinned.'
    }
}

Write-Host 'Packaged local demo started (viewer capped at 30 fps, idle priority).'
