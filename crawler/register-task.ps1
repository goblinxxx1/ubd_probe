# Registers a Windows Task Scheduler job that runs the crawler on an interval.
# Usage:  .\register-task.ps1 -IntervalMinutes 60
param([int]$IntervalMinutes = 60)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "venv python not found at $python" }

$action  = New-ScheduledTaskAction -Execute $python -Argument "-m crawler run" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "UBD Crawler" -Action $action -Trigger $trigger `
    -Settings $settings -Description "UBD offers crawler (one pass per interval)" -Force

Write-Host "Registered 'UBD Crawler' to run every $IntervalMinutes minute(s)."
