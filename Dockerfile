# ==========================================
# 🌌 【天道】修仙小说多智能体创作引擎 - 生产级 Dockerfile
# ==========================================
FROM python:3.12-slim

# 设置工作目录与核心环境变量
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# ---------------------------------------------------------------------------
# 系统级基础依赖：tzdata（时区）+ curl（健康检查）+ git（一键升级接口要用）
#
# 这一步以前会"一直卡住"，是三个原因叠在一起，少解决一个就会复发：
#   1) 没设 DEBIAN_FRONTEND=noninteractive
#      → tzdata 的 debconf 交互界面在无 TTY 的构建环境里等输入，永远等不到
#   2) 直连 deb.debian.org / security.debian.org
#      → 国内网络极慢甚至不可达，apt-get update 长时间一行输出都没有
#   3) 没给超时与重试
#      → 连接卡死时 apt 不会自己放弃，表现就是"永远停在 [3/7]"
#
# 对应处理：非交互安装 + 换国内镜像源（可用 --build-arg 关掉）+ 强制 IPv4
#          + 15 秒超时 + 5 次重试
#   换源关掉：docker build --build-arg APT_MIRROR= .
#   换别的源：docker build --build-arg APT_MIRROR=mirrors.tuna.tsinghua.edu.cn .
# ---------------------------------------------------------------------------
ARG APT_MIRROR=mirrors.aliyun.com
ARG APT_RETRIES=5

RUN set -eux; \
    if [ -n "${APT_MIRROR}" ]; then \
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do \
            [ -f "$f" ] || continue; \
            sed -i -e "s|deb.debian.org|${APT_MIRROR}|g" -e "s|security.debian.org|${APT_MIRROR}|g" "$f"; \
        done; \
    fi; \
    export DEBIAN_FRONTEND=noninteractive; \
    APT_OPTS="-o Acquire::Retries=${APT_RETRIES} -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15 -o Acquire::ForceIPv4=true"; \
    apt-get ${APT_OPTS} update; \
    apt-get ${APT_OPTS} install -y --no-install-recommends tzdata curl git ca-certificates; \
    ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime; \
    echo "${TZ}" > /etc/timezone; \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖文件并利用 Docker 缓存层
# PIP_INDEX_URL 留空即用官方 PyPI；国内若 pip 也慢，用
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=

COPY requirements.txt /app/requirements.txt

RUN set -eux; \
    if [ -n "${PIP_INDEX_URL}" ]; then PIP_INDEX="--index-url ${PIP_INDEX_URL}"; else PIP_INDEX=""; fi; \
    pip install --no-cache-dir --retries 5 --timeout 30 ${PIP_INDEX} -r requirements.txt

# 复制源码
COPY . /app

# 创建数据持久化目录
RUN mkdir -p /app/output

# 暴露端口：8088 (Web控制台与HTTP API), 8089 (WebSocket推演流)
EXPOSE 8088 8089

# 容器健康检查（服务端监听的是 0.0.0.0:8088，这里固定用 127.0.0.1 避免 localhost 先解析到 ::1）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS --max-time 5 http://127.0.0.1:8088/api/status > /dev/null || exit 1

# 启动天道服务
CMD ["python", "web_server.py", "8088"]
