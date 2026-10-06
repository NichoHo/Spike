# Registers a Windows scheduled task that starts Spike (web + worker + watcher) at boot,
# with no window. run_spike.cmd restarts Spike if it exits. Run once from an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
# Remove with: Unregister-ScheduledTask -TaskName Spike -Confirm:$false

$root = Split-Path -Parent $PSScriptRoot
$cmd = Join-Path $PSScriptRoot "run_spike.cmd"
$log = Join-Path $root "data\spike.log"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -WorkingDirectory $root -Argument "/c `"$cmd`""

$trigger = New-ScheduledTaskTrigger -AtStartup

# S4U: runs whether or not you are signed in, without storing your password, and with no window.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Spike" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered task 'Spike'. Start it now with: Start-ScheduledTask -TaskName Spike"
Write-Host "Log file: $log"
Write-Host "Keep the PC awake, or nothing runs while it sleeps:"
Write-Host "  Settings > System > Power > Screen and sleep > 'When plugged in, put my device to sleep after' = Never"
