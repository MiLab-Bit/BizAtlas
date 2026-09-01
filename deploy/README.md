# BizAtlas 私有化部署包（P0-② 最小合规）

目标：**数据不出域、鉴权默认开启、一键起服务**。适用于中小金融机构内网 /
专有云部署，满足「私有化小模型 + 可审计」的差异化定位。

## 组件
- `Dockerfile` — 基于 python:3.11-slim，依赖先装（层缓存），密钥经 `.env` 注入。
- `docker-compose.yml` — 单服务，卷持久化 `data/uploads/exports`，带健康检查。
- `.env.example` — 全部环境变量模板（含鉴权/LLM/数据源/视觉后端）。
- `privatize.sh` — 一键生成强随机 `AUTH_SECRET`/`BOOTSTRAP_TOKEN`/`INTEGRITY_SECRET`，
  并强制 `BIZATLAS_AUTH_DISABLED=false`。

## 步骤
```bash
cp .env.example .env          # 填写 LLM / 数据源密钥
./privatize.sh                # 生成鉴权与签名密钥（幂等）
docker compose up -d          # 起服务
curl http://127.0.0.1:8000/v1/healthz
```

## 首管理员引导
部署后访问 `POST /v1/admin/bootstrap`，Header 带 `X-Bootstrap-Token: <BOOTSTRAP_TOKEN>`，
创建首个 admin 账号，随后用其令牌调用其余端点。

## 合规要点
- 鉴权关闭开关 `BIZATLAS_AUTH_DISABLED` 在私有化镜像中默认 `false`。
- 报告完整性签名 `BIZATLAS_INTEGRITY_SECRET` 缺失时报告会降级告警（已在 bootstrap 自检）。
- 所有数据源未配置即优雅降级，不阻断启动；运行时实际启用状态由
  `GET /v1/compliance/statement` 与 `GET /v1/health` 显式暴露。
- 审计：登录类事件 + 每个敏感 API 调用均写入 `audit_log`（append-only）。
