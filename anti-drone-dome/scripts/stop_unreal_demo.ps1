<# Stops only the local auto-repeat simulator and its Unreal bridge. #>

function Stop-AegisDemoProcessTree([int]$ProcessId) {
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId } |
        ForEach-Object { Stop-AegisDemoProcessTree $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match '(?i)(integration\\unreal_bridge\.py|main\.py.*--(auto-start|demo-repeat|external-viewer-only|swarm))'
} | ForEach-Object { Stop-AegisDemoProcessTree $_.ProcessId }

Write-Host 'Local demo helpers stopped. Unreal remains open.'
