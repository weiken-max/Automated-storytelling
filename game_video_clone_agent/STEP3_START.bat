@echo off
setlocal
echo =========================================================
echo [STEP 1] Cleaning old processes...
echo =========================================================
wmic process where "commandline like '%%feishu/%%'" call terminate >nul 2>&1

echo =========================================================
echo [STEP 2] Starting Hidden Director (Hub)...
echo =========================================================
if exist venv (
    call venv\Scripts\activate
)

powershell -Command "Start-Process python -ArgumentList 'feishu/watchdog.py' -WorkingDirectory '%CD%' -WindowStyle Hidden"

echo =========================================================
echo [OK] Bot is ONLINE in HIDDEN mode!
echo Send 'status' to verify (Natural Language works too).
echo =========================================================
pause
