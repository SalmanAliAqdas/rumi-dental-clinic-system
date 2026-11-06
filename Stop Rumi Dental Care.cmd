@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\trial_launcher.py" --stop
if errorlevel 1 pause
