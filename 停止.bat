@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title 停止 AI Learning Copilot
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev.ps1"
echo.
echo [完成] 已停止。数据库容器仍在运行，数据不会丢。
ping -n 6 127.0.0.1 >nul