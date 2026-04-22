@echo off
REM USD/EGP daily summary — invoked at 8 AM and 8 PM Cairo by Task Scheduler.
cd /d "%~dp0"
python daily_summary.py >> "%~dp0daily.log" 2>&1
exit /b %ERRORLEVEL%
