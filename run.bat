@echo off
chcp 65001 >nul
echo =======================================================
echo    启动【天道】多智能体凡人流修仙小说演化系统
echo =======================================================
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py %*
pause
