@echo off
chcp 65001 >nul
title 天道 - Docker 一键部署与自动更新系统
echo ========================================================
echo   【天道】修仙小说多智能体创作引擎 - Docker 一键管理
echo ========================================================
echo.

where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未在系统检测到 Docker，请先安装并启动 Docker Desktop:
    echo 官方下载: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

if not exist output mkdir output

set ACTION=%1
if "%ACTION%"=="" set ACTION=menu

if "%ACTION%"=="menu" (
    echo 请选择要执行的操作:
    echo  [1] 一键启动 / 重新部署 (docker compose up -d --build)
    echo  [2] 一键在线自动更新代码并重启 (Git pull ^& 重建)
    echo  [3] 查看容器实时日志 (docker compose logs -f)
    echo  [4] 重启容器服务 (docker compose restart)
    echo  [5] 停止并移除容器 (docker compose down)
    echo  [6] 退出
    echo.
    set /p CHOICE="请输入数字 [1-6]: "
    if "!CHOICE!"=="1" goto do_deploy
    if "!CHOICE!"=="2" goto do_update
    if "!CHOICE!"=="3" goto do_logs
    if "!CHOICE!"=="4" goto do_restart
    if "!CHOICE!"=="5" goto do_stop
    if "!CHOICE!"=="6" exit /b 0
    goto do_deploy
)

if "%ACTION%"=="deploy" goto do_deploy
if "%ACTION%"=="update" goto do_update
if "%ACTION%"=="logs" goto do_logs
if "%ACTION%"=="restart" goto do_restart
if "%ACTION%"=="stop" goto do_stop

:do_deploy
echo [*] 正在构建镜像并启动容器...
docker compose up -d --build
if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo   [成功] 天道容器已成功在后台启动！
    echo   网页控制台: http://localhost:28088
    echo   WebSocket: ws://localhost:28089
    echo   持久化目录: .\output (配置与作品永久保存)
    echo ========================================================
) else (
    echo [错误] 启动失败，请检查 Docker Desktop 是否正常运行。
)
echo.
pause
exit /b 0

:do_update
echo [*] 正在拉取远程 GitHub 最新提交...
git pull origin main
echo [*] 重新构建镜像并平滑重启...
docker compose up -d --build
echo.
echo [成功] 代码已更新完毕，天道容器已重新载入！
echo.
pause
exit /b 0

:do_logs
docker compose logs -f
exit /b 0

:do_restart
docker compose restart
echo [已重启]
pause
exit /b 0

:do_stop
docker compose down
echo [已停止]
pause
exit /b 0
