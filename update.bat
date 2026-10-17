@echo off
chcp 65001 >nul
title 天道系统 - 在线代码更新与升级
echo ========================================================
echo   🌌 【天道】多智能体修仙小说创作引擎 · 在线更新
echo ========================================================
echo.

where git >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未在系统环境变量中检测到 Git，请先安装 Git 后再执行更新！
    echo 下载地址: https://git-scm.com/
    pause
    exit /b 1
)

echo [*] 正在检查并拉取 GitHub 最新版本代码...
git fetch --all
git pull origin main

if %ERRORLEVEL% neq 0 (
    echo.
    echo [提示] git pull 执行遇到冲突或未配置远程仓库，尝试同步最新分支...
    git pull
)

echo.
echo [*] 正在更新 Python 依赖环境...
pip install -r requirements.txt --quiet --upgrade

echo.
echo ========================================================
echo   ✅ 更新完毕！当前版本已同步至最新。
echo   您可随时运行 start_web.bat 重启网页控制台。
echo ========================================================
echo.
pause
