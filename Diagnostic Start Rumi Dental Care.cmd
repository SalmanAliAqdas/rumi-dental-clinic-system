@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\trial_launcher.py" --no-browser
if errorlevel 1 pause
