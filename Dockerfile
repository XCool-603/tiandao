# ==========================================
# 🌌 【天道】修仙小说多智能体创作引擎 - 生产级 Dockerfile
# ==========================================
FROM python:3.12-slim

# 设置工作目录与核心环境变量
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# 安装系统级基础依赖（时区与健康检查所需 curl）
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata curl git && \
    ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime && \
    echo ${TZ} > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖文件并利用 Docker 缓存层
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . /app

# 创建数据持久化目录
RUN mkdir -p /app/output

# 暴露端口：8088 (Web控制台与HTTP API), 8089 (WebSocket推演流)
EXPOSE 8088 8089

# 容器健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8088/api/status || exit 1

# 启动天道服务
CMD ["python", "web_server.py", "8088"]
