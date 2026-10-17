@echo off
chcp 65001 >nul
echo =======================================================
echo    🌌 正在启动【天道】大千演化台网页控制中心...
echo =======================================================
set PYTHON_CMD=python
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
start "" http://localhost:8088
"%PYTHON_CMD%" web_server.py 8088
pause
