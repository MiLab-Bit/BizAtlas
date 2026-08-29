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
