# ============================================================================
# USD/EGP Tracker - Local Windows setup
# ----------------------------------------------------------------------------
# What this script does (one-time, idempotent):
#   1. Verifies Python is installed and installs pip requirements
#   2. Creates a .env file with your Telegram credentials (prompts if missing)
#   3. Registers two Windows Scheduled Tasks:
#        - USD-EGP-Tracker  -> every 15 min (script auto-silences 12 AM-8 AM)
#        - USD-EGP-Daily    -> 8:00 AM and 8:00 PM
#   4. Runs the tracker once to verify everything works
#
# Usage: right-click this file -> Run with PowerShell
#        OR in a terminal:  powershell -ExecutionPolicy Bypass -File setup_local.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$RepoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoPath

Write-Host "`n=== USD/EGP Tracker - Local Setup ===" -ForegroundColor Cyan
Write-Host "Repo path: $RepoPath`n"

# --- 1. Python check ---
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "    $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "    ERROR: Python not found on PATH. Install from python.org first." -ForegroundColor Red
    exit 1
}

# --- 2. Install Python dependencies ---
Write-Host "`n[2/5] Installing Python dependencies..." -ForegroundColor Yellow
& python -m pip install --quiet --upgrade pip
& python -m pip install --quiet -r requirements.txt
Write-Host "    Dependencies installed." -ForegroundColor Green

# --- 3. .env file ---
Write-Host "`n[3/5] Checking .env credentials..." -ForegroundColor Yellow
$envPath = Join-Path $RepoPath ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "    .env not found. Creating it now." -ForegroundColor Yellow
    $token = Read-Host "    Enter your TELEGRAM_BOT_TOKEN"
    $chatId = Read-Host "    Enter your TELEGRAM_CHAT_ID"
    $envContent = @"
# USD/EGP Tracker - local credentials (do NOT commit this file)
TELEGRAM_BOT_TOKEN=$token
TELEGRAM_CHAT_ID=$chatId
# Optional overrides:
# PRIMARY_SOURCE=CIB
# MIN_CHANGE=0.05
"@
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Write-Host "    .env created." -ForegroundColor Green
} else {
    Write-Host "    .env already exists - skipping." -ForegroundColor Green
}

# --- 4. Register Scheduled Tasks ---
Write-Host "`n[4/5] Registering Windows Scheduled Tasks..." -ForegroundColor Yellow

$trackerBat = Join-Path $RepoPath "run_tracker.bat"
$dailyBat   = Join-Path $RepoPath "run_daily.bat"

# Remove any existing tasks first (clean re-install)
foreach ($name in @("USD-EGP-Tracker", "USD-EGP-Daily")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "    Removed existing task: $name" -ForegroundColor Gray
    }
}

# Tracker: every 15 min, starting at the next quarter-hour, forever
$trackerAction = New-ScheduledTaskAction -Execute $trackerBat
$startTime = (Get-Date).Date.AddHours((Get-Date).Hour).AddMinutes(([int]((Get-Date).Minute / 15) + 1) * 15)
$trackerTrigger = New-ScheduledTaskTrigger -Once -At $startTime `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration ([TimeSpan]::FromDays(3650))
$trackerSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "USD-EGP-Tracker" `
    -Action $trackerAction -Trigger $trackerTrigger -Settings $trackerSettings `
    -Description "Checks USD/EGP rate every 15 min; silent 12 AM-8 AM Cairo." | Out-Null
Write-Host "    Registered: USD-EGP-Tracker (every 15 min, first run at $startTime)" -ForegroundColor Green

# Daily summary: 8 AM and 8 PM every day
$dailyAction = New-ScheduledTaskAction -Execute $dailyBat
$dailyTrigger1 = New-ScheduledTaskTrigger -Daily -At 8:00AM
$dailyTrigger2 = New-ScheduledTaskTrigger -Daily -At 8:00PM
Register-ScheduledTask -TaskName "USD-EGP-Daily" `
    -Action $dailyAction -Trigger @($dailyTrigger1, $dailyTrigger2) -Settings $trackerSettings `
    -Description "USD/EGP daily summary: 8 AM (Morning Briefing) + 8 PM (Evening Wrap-up)." | Out-Null
Write-Host "    Registered: USD-EGP-Daily (8:00 AM + 8:00 PM daily)" -ForegroundColor Green

# --- 5. Verification run ---
Write-Host "`n[5/5] Running tracker once to verify..." -ForegroundColor Yellow
& python tracker.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== Setup complete! ===" -ForegroundColor Cyan
    Write-Host "Check your Telegram for the confirmation message." -ForegroundColor Green
    Write-Host ""
    Write-Host "Your scheduled tasks are visible in:"
    Write-Host "  Task Scheduler  >  Task Scheduler Library  >  USD-EGP-*"
    Write-Host ""
    Write-Host "Logs are written to:"
    Write-Host "  $RepoPath\tracker.log"
    Write-Host "  $RepoPath\daily.log"
    Write-Host ""
    Write-Host "To remove everything later, run:  .\uninstall_local.ps1"
} else {
    Write-Host "`nERROR: tracker.py exited with code $LASTEXITCODE." -ForegroundColor Red
    Write-Host "Check your .env credentials and try again." -ForegroundColor Red
    exit 1
}
