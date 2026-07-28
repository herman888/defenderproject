<# Stops only the local auto-repeat simulator and its Unreal bridge. #>

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and (
        $_.CommandLine -like '*integration\unreal_bridge.py*' -or
        $_.CommandLine -like '*main.py*--demo-repeat*'
    )
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Write-Host 'Local demo helpers stopped. Unreal remains open.'
