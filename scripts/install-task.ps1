# Registers a daily 7:00 AM task named "Bid Radar Daily Sweep" for the current user.
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\run-sweep.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "Bid Radar Daily Sweep" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Registered 'Bid Radar Daily Sweep' (daily 7:00 AM) -> $script"
