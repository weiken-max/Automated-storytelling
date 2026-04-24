@echo off
setlocal
echo =========================================================
echo [STEP 1] Checking Python installation...
echo =========================================================
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found or not in PATH.
    pause
    exit /b
)
echo [OK] Python found.

echo =========================================================
echo [STEP 2] Creating Virtual Environment (venv)...
echo =========================================================
if not exist venv (
    python -m venv venv
)
echo [OK] Venv ready.

echo =========================================================
echo [STEP 3] Installing dependencies (Please wait)...
echo =========================================================
call venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo =========================================================
echo [OK] ALL DONE! Environment is ready.
echo =========================================================
pause
