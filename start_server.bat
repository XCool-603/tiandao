@echo off
chcp 65001 >nul
title 天道 · 多智能体修仙演化系统
echo ========================================================
echo   🌌 启动【天道】大千演化台服务...
echo   服务地址: http://localhost:8088
echo ========================================================
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" web_server.py 8088
pause
