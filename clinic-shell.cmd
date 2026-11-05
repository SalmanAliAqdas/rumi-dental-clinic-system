@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
set "DJANGO_SETTINGS_MODULE=config.settings"
set "RUMI_DATA_DIR=%~dp0runtime\development"
if not exist "%~dp0.venv\Scripts\python.exe" goto python_error
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\trial_launcher.py" --check
if errorlevel 1 goto check_error
powershell.exe -NoLogo -NoProfile -NoExit -Command "Write-Host 'Rumi Dental Care - Phase 1 clinic shell'; Write-Host ('Working directory: ' + (Get-Location).Path); Write-Host ('Settings: ' + $env:DJANGO_SETTINGS_MODULE); Write-Host ('Data directory: ' + $env:RUMI_DATA_DIR); Write-Host 'Use .\.venv\Scripts\python.exe manage.py for account commands. Passwords belong only in local hidden prompts.'"
exit /b %ERRORLEVEL%
:directory_error
echo Unable to open the project folder containing this launcher.
pause
exit /b 1
:python_error
echo The project's .venv\Scripts\python.exe is missing.
echo Restore or manually set up the documented virtual environment first.
:check_error
pause
exit /b 1
