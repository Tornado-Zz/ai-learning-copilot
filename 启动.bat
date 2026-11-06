@echo off
REM Double-click this file to start AI Learning Copilot.
REM It stops anything left on ports 3000/8000 first, then runs scripts\start-dev.ps1.
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title AI Learning Copilot
echo ============================================
echo   正在启动 AI Learning Copilot
echo   首次启动要装依赖并构建前端，约 2-3 分钟
echo   之后一般 10-20 秒
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev.ps1"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo [失败] 启动脚本返回 %RC%。请把上面的错误信息发给我。
  pause
  exit /b %RC%
)
start "" http://127.0.0.1:3000
echo.
echo [完成] 浏览器应已自动打开 http://127.0.0.1:3000
echo 停止服务请双击 停止.bat
echo.
ping -n 9 127.0.0.1 >nul