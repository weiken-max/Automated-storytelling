@echo off
setlocal
echo =========================================================
echo [STEP 1] Starting Baidu Netdisk Authentication...
echo =========================================================
if exist venv (
    call venv\Scripts\activate
)
python -m bypy info
echo =========================================================
echo If you see your storage quota, authentication SUCCESS!
echo =========================================================
pause
