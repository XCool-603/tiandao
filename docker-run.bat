@echo off
chcp 65001 >nul
title 天道 - Docker 一键启动
echo ========================================================
echo   🌌 【天道】修仙小说多智能体创作引擎 - Docker 一键部署
echo ========================================================
echo.

where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未在系统环境变量中检测到 Docker，请先安装并启动 Docker Desktop:
    echo 官方下载: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

echo [*] 正在构建镜像并启动容器...
docker compose up -d --build

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo   ✅ 天道容器已成功在后台启动！
    echo   🌐 网页控制台: http://localhost:8088
    echo   ⚡ WebSocket: ws://localhost:8089/ws/simulate
    echo   📜 查看实时日志: docker compose logs -f
    echo   ⏹ 停止容器: docker compose down
    echo ========================================================
    echo.
) else (
    echo.
    echo ❌ Docker 启动失败，请检查 Docker Desktop 是否已开启。
    echo.
)
pause
