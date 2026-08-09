# BizAtlas / 商舆 · 阶段 3 部署运行手册

本目录提供容器化与编排骨架，配合 `apps/api`（FastAPI）实现企业化部署：
RBAC 鉴权、可观测（日志/指标/追踪）、高可用（健康探针 + 重启策略 + 状态持久化）。

## 1. 目录

- `Dockerfile`：基于 `python:3.12-slim` 的单阶段镜像，内置 liveness 健康检查。
- `docker-compose.yml`：单服务编排，`restart: unless-stopped` + 健康检查 + 数据卷。
- `.dockerignore`：排除本地 venv / 数据 / 前端依赖，控制镜像体积。

## 2. 本地构建与启动

```bash
# 在仓库根目录
docker build -f deploy/Dockerfile -t bizatlas:0.3.0 .
docker run --rm -p 8000:8000 bizatlas:0.3.0

# 或用 compose（含持久化卷与环境）
cd deploy && docker compose up --build
```

启动后探测：
- 存活：`GET /v1/health/live`
- 就绪：`GET /v1/health/ready`（检查 DB 可达）
- 指标：`GET /v1/metrics`（Prometheus 文本）/ `?fmt=json`

## 3. 鉴权（RBAC）开启

默认 `BIZATLAS_AUTH_DISABLED=true`：等价 ADMIN 全放行，前端/演示无感。
生产开启：

```bash
export BIZATLAS_AUTH_DISABLED=false
export BIZATLAS_AUTH_SECRET="<强随机密钥>"
```

调用方在请求头带令牌（HMAC，由 `bizatlas.auth.rbac.issue_token` 签发）：

```
Authorization: Bearer <token>
```

角色与权限矩阵（最小权限）：

| 角色 | 权限域 |
| --- | --- |
| viewer | 读 |
| analyst | 读 / 写 / 调用工具 / 导出报告 |
| reviewer | 读 / 复核通过 / 复核驳回 |
| admin | 全部（含角色/审计管理） |

受门禁的端点示例：`/v1/providers/akshare/fetch`（tool:call）、
`/v1/rules/.../activate`（rules:manage）、报告导出 confirm（reports:export）、
`/v1/workflows/{id}/review`（复核）、`/v1/admin/rbac`（admin）。

## 4. 高可用与扩展

- API 服务**无状态**：确定性评分内核 + 外部数据源降级，多副本前置 LB 即可水平扩展。
- 持久状态（SQLite / 上传 / 导出）已通过卷挂载，升级镜像不丢数据。
- 生产建议将 SQLite 替换为托管 Postgres（改动集中在 `bizatlas/data/db.py`）。
- 指标接入 Prometheus + Grafana；日志为结构化 JSON，直接喂 Loki/ELK。

## 5. 工具治理（运行期）

启动自动注册受治理工具（权限 + 熔断 + 沙箱）：
- `rag.search`（本地检索，离线可用）
- `data.provider_fetch`（外部数据源，沙箱隔离 + 熔断）
- `ingest.vision_parse`（视觉解析，沙箱隔离 + 熔断）

外部后端连续失败会自动熔断（快速失败防雪崩）；单次挂起由沙箱超时强制终止。

---

## 6. 生产服务器独立部署（systemd + nginx，无 Docker）

适用于阿里云 ECS 等裸机。配套产物：`bizatlas.service`、`bizatlas_nginx.conf`。当前生产实例：服务器 `47.103.102.36`，目录 `/opt/bizatlas`，访问 `http://47.103.102.36:8080/`。

### 6.1 前置：Python ≥3.11
系统自带 Python 通常 <3.11（如 Alibaba Cloud Linux 3 自带 3.6.8），需另装 3.11 并建 venv：

```bash
python3.11 -m venv /opt/bizatlas/venv
/opt/bizatlas/venv/bin/python -m pip install -r requirements.txt
/opt/bizatlas/venv/bin/python -m pip install -e .   # editable 必装，否则 No module named 'bizatlas'
```

> editable 安装必做；venv 移动目录后 bin 脚本 shebang 会失效，pip 一律改用 `python -m pip`。

### 6.2 传输代码 + 放置单元 / 站点
```bash
# 传代码（排除 node_modules/.git/__pycache__）
tar czf - --exclude=node_modules --exclude=.git --exclude='*.pyc' --exclude=__pycache__ . \
  | ssh root@host 'tar xzf - -C /opt/bizatlas'

# ⚠️ 不要用 --exclude='data'：会误伤源码 packages/bizatlas/data，改用 find 精确补回
find packages apps -type d -name data | tar --null -czf - -T - \
  | ssh root@host 'tar xzf - -C /opt/bizatlas'

# 前端需先构建
cd apps/web && npm install && npm run build    # 产物 apps/web/dist

# 放置 systemd 单元与 nginx 站点
cp deploy/bizatlas.service /etc/systemd/system/bizatlas.service
cp deploy/bizatlas_nginx.conf /etc/nginx/conf.d/bizatlas.conf
systemctl daemon-reload && systemctl enable --now bizatlas
nginx -t && systemctl reload nginx
```

### 6.3 验证
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/            # 前端 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/v1/health  # 200
curl -N "http://127.0.0.1:8080/v1/analyze/pipeline/stream?company_id=risky&task=analyze_risk"  # SSE 流
systemctl is-active bizatlas
```
- 健康检查端点为 `/v1/health`（**非** `/live`、`/ready`）。
- 端口冲突：`nginx -t` 报 `conflicting server name "_" on ...:8080` → 8080 上有别的 `server_name "_"` 块，删残留 conf 即可。

### 6.4 网络
服务器若无 firewalld，公网访问 8080 需在**云安全组放行 8080 入站**（FastToken 的 80/443 不受影响）。

### 6.5 重命名 / 迁移目录
若从旧目录（如 `/opt/gopa`）迁移：移动后务必在**新路径**重跑 `python -m pip install -e .` 重注册 editable，否则 import 失败。
