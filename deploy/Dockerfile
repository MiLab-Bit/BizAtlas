# BizAtlas 私有化部署镜像（P0-② 最小合规 · 数据不出域）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/bizatlas

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY . .

# 密钥与运行时配置通过 .env（gitignore）注入，不进镜像
RUN mkdir -p uploads exports data content/fixtures

# 鉴权默认开启；privatize.sh 会生成 BIZATLAS_AUTH_SECRET 与 BOOTSTRAP_TOKEN
ENV BIZATLAS_AUTH_DISABLED=false

EXPOSE 8000

CMD ["uvicorn", "apps.api.launcher:app", "--host", "0.0.0.0", "--port", "8000"]
