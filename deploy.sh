#!/usr/bin/env bash
# ========================================================
# 天道 - Docker 生产环境一键部署与全自动更新守护脚本
# 支持 Linux / macOS / 云服务器 (Ubuntu / Debian / CentOS / Alpine)
# ========================================================
set -e

APP_NAME="天道 (Tiandao)"
PORT="${TIANDAO_HOST_PORT:-28088}"
WS_PORT="${TIANDAO_HOST_WS_PORT:-28089}"

echo "========================================================"
echo "  【${APP_NAME}】Docker 一键部署 & 自动热更新引擎"
echo "========================================================"
echo ""

# 1. 检测与安装 Docker / Docker Compose
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "[提示] 检测到当前系统未安装 Docker，准备自动安装官方 Docker 环境..."
        if command -v curl &> /dev/null; then
            curl -fsSL https://get.docker.com | bash
        elif command -v wget &> /dev/null; then
            wget -qO- https://get.docker.com | bash
        else
            echo "[错误] 缺少 curl 或 wget，请先手动安装 docker: https://docs.docker.com/get-docker/"
            exit 1
        fi
        systemctl enable docker && systemctl start docker
    fi

    # 检测 docker compose 或 docker-compose
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        echo "[提示] 正在安装 docker compose 插件..."
        apt-get update && apt-get install -y docker-compose-plugin || true
        DOCKER_COMPOSE="docker compose"
    fi
}

check_docker

# 2. 检查输出数据持久化目录
mkdir -p output

# 3. 参数分流处理
ACTION="${1:-deploy}"

case "$ACTION" in
    update)
        echo "[*] 正在执行全自动更新..."
        if [ -d ".git" ] && command -v git &> /dev/null; then
            echo "[*] 拉取 GitHub main 分支最新提交..."
            git pull origin main
        else
            echo "[*] 免 Git 环境：下载并解压官方最新 release/main..."
            curl -L https://github.com/XCool-603/tiandao/archive/refs/heads/main.zip -o /tmp/tiandao_update.zip
            unzip -o -q /tmp/tiandao_update.zip -d /tmp/tiandao_extracted
            cp -rf /tmp/tiandao_extracted/tiandao-main/* ./
            rm -rf /tmp/tiandao_update.zip /tmp/tiandao_extracted
        fi
        echo "[*] 重新构建并平滑重启容器..."
        $DOCKER_COMPOSE down --remove-orphans
        $DOCKER_COMPOSE up -d --build
        echo ""
        echo "[成功] 天道已成功更新并无缝重启！"
        echo "控制台地址: http://localhost:${PORT}"
        ;;
    stop)
        echo "[*] 正在停止服务..."
        $DOCKER_COMPOSE down
        echo "[已停止]"
        ;;
    restart)
        echo "[*] 正在重启服务..."
        $DOCKER_COMPOSE restart
        echo "[已重启]"
        ;;
    logs)
        $DOCKER_COMPOSE logs -f
        ;;
    watch)
        echo "========================================================"
        echo "  已启用天道与 Watchtower 自动更新守护模式"
        echo "  每隔 5 分钟自动扫描并拉取最新镜像/代码自动升级"
        echo "========================================================"
        $DOCKER_COMPOSE up -d --build
        # 启动 watchtower 自动监听更新
        docker run -d \
            --name tiandao-watchtower \
            --restart unless-stopped \
            -v /var/run/docker.sock:/var/run/docker.sock \
            containrrr/watchtower \
            --interval 300 \
            --cleanup \
            tiandao
        echo "[守护就绪] 自动更新服务已就绪！"
        ;;
    deploy|*)
        echo "[*] 开始构建并启动天道生产级容器..."
        $DOCKER_COMPOSE up -d --build

        echo ""
        echo "========================================================"
        echo "  [成功] 天道已成功在后台启动！"
        echo "  Web 控制台访问: http://localhost:${PORT}"
        echo "  WebSocket 通道: ws://localhost:${WS_PORT}"
        echo "  常用管理命令:"
        echo "    查看实时日志: ./deploy.sh logs"
        echo "    一键拉取最新: ./deploy.sh update"
        echo "    停止当前服务: ./deploy.sh stop"
        echo "    重启当前服务: ./deploy.sh restart"
        echo "    挂载配置位置: ./output/.env 与 ./output/system_config.json"
        echo "========================================================"
        echo ""
        ;;
esac
