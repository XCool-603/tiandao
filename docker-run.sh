#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  🌌 【天道】修仙小说多智能体创作引擎 - Docker 一键启动"
echo "========================================================"
echo ""

if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 未检测到 Docker 环境，请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "[*] 正在构建镜像并启动容器..."
docker compose up -d --build

echo ""
echo "✅ 天道容器已成功在后台启动！"
echo "🌐 网页控制台: http://localhost:8088"
echo "⚡ WebSocket: ws://localhost:8089/ws/simulate"
echo "📜 查看运行日志: docker compose logs -f"
echo "⏹ 停止服务: docker compose down"
echo ""
