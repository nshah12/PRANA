# Run this ONCE (as Administrator) to register PRANA startup with Windows Task Scheduler.
# After registration, prana_start.ps1 runs automatically on every login.
#
# Usage:
#   Right-click PowerShell → Run as Administrator
#   cd C:\Nilesh\claude-code
#   .\scripts\register_startup.ps1

$SCRIPT = "C:\Nilesh\claude-code\scripts\prana_start.ps1"
$TASK_NAME = "PRANA Dev Stack Startup"

# Remove old task if exists
Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File `"$SCRIPT`" -Quiet"

# Trigger: on login of current user, with 30-second delay (lets Docker Desktop start first)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT30S"   # 30-second delay

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Description "Starts PRANA local dev stack (Docker containers + API + Portal) on login." `
    -Force

Write-Host ""
Write-Host "Registered: '$TASK_NAME'" -ForegroundColor Green
Write-Host "Runs 30 seconds after login as: $env:USERNAME" -ForegroundColor Green
Write-Host ""
Write-Host "To remove:  Unregister-ScheduledTask -TaskName '$TASK_NAME' -Confirm:`$false"
Write-Host "To run now: .\scripts\prana_start.ps1"
Write-Host ""
