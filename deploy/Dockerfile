# BizAtlas / 商舆 · 阶段 3 部署镜像
# 单阶段：python:3.12-slim + 源码可编辑安装；生产可改为多阶段以减小体积。
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BIZATLAS_ENV=prod \
    BIZATLAS_MODE=snapshot \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# 先装依赖（利用层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 再拷源码并安装（editable，保证 bizatlas / apps 均可导入）
COPY . /app
RUN pip install --no-cache-dir -e .

EXPOSE 8000

# 高可用：liveness 探针（进程存活即 200）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health/live').status==200 else 1)"

# 启动 API（容器内由 launcher 读取配置并注册受治理工具）
CMD ["python", "-m", "apps.api.launcher"]
