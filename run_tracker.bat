@echo off
REM USD/EGP tracker — invoked by Windows Task Scheduler every 15 minutes.
REM The Python script gates quiet hours internally (silent 12 AM - 8 AM Cairo).
cd /d "%~dp0"
python tracker.py >> "%~dp0tracker.log" 2>&1
exit /b %ERRORLEVEL%
