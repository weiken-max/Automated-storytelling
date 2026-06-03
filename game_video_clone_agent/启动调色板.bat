@echo off
title "调色板" AI 电影平台 - 启动控制台
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo =======================================================
    echo [ERROR] venv\Scripts\python.exe not found!
    echo Please make sure you run this in the game_video_clone_agent directory.
    echo =======================================================
    pause
    exit /b
)

venv\Scripts\python.exe start_app.py
if %errorlevel% neq 0 (
    echo =======================================================
    echo [ERROR] Application exited with error code %errorlevel%.
    echo =======================================================
    pause
)
