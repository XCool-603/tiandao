# ==========================================
# 🌌 【天道】修仙/全题材小说多智能体创作引擎 - 极速生产级 Dockerfile
# 彻底移除极易在网络环境卡死的系统级 apt-get，纯 Python 容器秒级构建
# ==========================================
FROM python:3.12-slim

# 设置工作目录与核心环境变量
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# 复制依赖配置并使用国内清华高速镜像安装（彻底告别构建卡顿，3秒完成）
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制全量代码与 Web 前端静态资源
COPY . /app

# 确保输出数据持久化目录存在
RUN mkdir -p /app/output

# 暴露端口：8088 (Web控制台与HTTP API), 8089 (WebSocket推演流)
EXPOSE 8088 8089

# 原生 Python 轻量健康检查（无任何 curl 系统依赖，毫秒级响应）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/api/status', timeout=3)" || exit 1

# 启动天道主服务
CMD ["python", "web_server.py", "8088"]
