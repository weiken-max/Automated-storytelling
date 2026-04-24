@echo off
setlocal
wmic process where "commandline like '%%hub.py%%'" call terminate >nul 2>&1
wmic process where "commandline like '%%watchdog.py%%'" call terminate >nul 2>&1

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if exist "%SCRIPT_DIR%\venv" (
    call "%SCRIPT_DIR%\venv\Scripts\activate"
)

powershell -Command "Start-Process python -ArgumentList 'feishu/watchdog.py' -WorkingDirectory '%SCRIPT_DIR%' -WindowStyle Hidden"
exit /b
