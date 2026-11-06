@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
set "DJANGO_SETTINGS_MODULE=config.settings"
set "RUMI_DATA_DIR=%~dp0runtime\development"
if not exist "%~dp0.venv\Scripts\python.exe" goto python_error
if "%~1"=="" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0scripts\desktop.pyw"
  exit /b 0
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\trial_launcher.py" %*
set "RUMI_LAUNCH_EXIT=%ERRORLEVEL%"
if not "%RUMI_LAUNCH_EXIT%"=="0" pause
exit /b %RUMI_LAUNCH_EXIT%
:directory_error
echo Unable to open the project folder containing this launcher.
pause
exit /b 1
:python_error
echo The project's .venv\Scripts\python.exe is missing.
echo Restore or manually set up the documented virtual environment first.
echo This launcher does not install packages or create a database.
pause
exit /b 1
