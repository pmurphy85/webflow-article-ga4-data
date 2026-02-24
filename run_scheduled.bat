@echo off
REM Run Webflow Article GA4 Traffic Tracker (for Task Scheduler or manual run)
REM Edit the paths below to match your setup.

set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

REM Use the project's venv if it exists; otherwise use default Python
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py
) else (
    python main.py
)

if errorlevel 1 pause
