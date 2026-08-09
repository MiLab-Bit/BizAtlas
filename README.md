# BizAtlas · 商舆工程仓库

> 产品名：**商舆**（BizAtlas）
> 定位：企业经营与风险研判 Agent —— 数据 + 规则 + 计算，可解释、可降级、人在回路。

面向「企业经营与风险研判」的金融服务 Agent——把金融分析师读资料、算风险、写报告的工作，压缩成一次上传、一句提问。

产品设计权威文档在上级目录 [`../`](../)（`00`–`10` 模块）。本仓库是**工程落地**：架构、契约、实现约束与代码。

---

## 一句话架构

```
上传资料 / 对话指令
        ↓
编排层（意图 → 任务图 → 人在回路）
        ↓
资料理解 → 规则匹配 → 风险研判 → 投研整理 → 流程辅助
        ↓
数据层（多源获取 · 三级降级 · 六维质检 · SQLite · 本地 RAG）
```

**关键数字走确定性计算；LLM 只做解析辅助与文案；结论处处可溯源。**

---

## 赛题五能力 ↔ 工程模块

| 赛题重点 | 工程包 | MVP 交付 |
|---|---|---|
| 资料理解 | `packages/ingest` + `packages/rag` + `packages/kg` | PDF/Excel 三表抽取 · 本地问答 · 引用溯源 |
| 规则匹配 | `packages/rules` | YAML 规则库 ≥20 条 · NL 新增 · 可解释命中 |
| 风险提示 | `packages/risk` | 五维评分 · GREEN–BLACK · 一页摘要 |
| 投研整理 | `packages/report` | 信用评估报告 · Word/PDF 导出 |
| 流程辅助 | `packages/workflow` | 贷前尽调模板（清单→研判→报告） |

---

## 仓库结构（目标）

```
BizAtlas/
├── README.md                 ← 本文件
├── doc/                      ← 工程文档（怎么建）
├── apps/
│   ├── api/                  ← FastAPI
│   └── web/                  ← React + Vite 工作台（ADR-005）
├── packages/
│   ├── contracts/            ← 共享 Schema / 类型
│   ├── ingest/               ← 文档解析与指标抽取
│   ├── data/                 ← 数据源适配 · 降级 · 质检
│   ├── rag/                  ← 本地检索
│   ├── kg/                   ← 知识图谱
│   ├── rules/                ← 规则引擎
│   ├── risk/                 ← 评分 · 压力测试 · 归因
│   ├── report/               ← 模板渲染与导出
│   └── workflow/             ← 流程模板与编排
├── content/
│   ├── rules/                ← 外置规则资产
│   ├── templates/            ← 报告模板
│   └── fixtures/             ← 演示案例（健康/风险/违约）
└── scripts/                  ← Spike · 烟测 · 建库
```

当前阶段：先冻结 **doc + README**，再按里程碑脚手架代码。详见 [`doc/09-directory-layout.md`](doc/09-directory-layout.md)。

---

## 文档入口

| 顺序 | 文档 | 读完应知道 |
|---|---|---|
| 1 | [doc/README.md](doc/README.md) | 文档地图与 PRD 关系 |
| 2 | [01-product-scope.md](doc/01-product-scope.md) | MVP 范围与 Non-goals |
| 3 | [02-architecture.md](doc/02-architecture.md) | 分层、边界、主序列 |
| 4 | [03-tech-stack.md](doc/03-tech-stack.md) | 选型与复用映射 |
| 5 | [04-data-layer.md](doc/04-data-layer.md) | 数据源、降级、表结构 |
| 6 | [05-agent-pipeline.md](doc/05-agent-pipeline.md) | 分析流水线六阶段 |
| 7 | [06-api-contracts.md](doc/06-api-contracts.md) | HTTP 契约 |
| 8 | [09-directory-layout.md](doc/09-directory-layout.md) | 代码树与依赖方向 |
| 9 | [10-milestones.md](doc/10-milestones.md) | W1–W4 交付 |
| 10 | [12-frontend-architecture.md](doc/12-frontend-architecture.md) | 雷达 Adopt · 工作台前端 |
| 11 | [13-features-and-differentiators.md](doc/13-features-and-differentiators.md) | 功能与特色 |
| — | [content/providers/registry.yaml](content/providers/registry.yaml) | 数据 API 占位（逐个点亮） |

冲突时：**验收口径以产品设计（PRD）为准；实现细节以 `doc/` + ADR 为准。**

---

## 设计原则（不可砍）

1. **能力与领域分离** — 算法内核通用；规则 / 模板外置可配置。
2. **可解释优先** — 每条结论输出「数据 → 计算 → 结论」链路。
3. **人在回路** — AI 出草稿与建议，人不确认不触发外部动作。
4. **降级不阻塞** — 数据 / 服务不可用时继续跑，明确标注 `_tier`。
5. **关键数字零幻觉** — 指标与评分强制走规则计算；LLM 不编数字。

---

## 快速状态

| 项 | 状态 |
|---|---|
| 产品设计（上级目录） | ✅ v1.0 |
| 工程文档 doc/ | ✅ |
| API + 规则/风险闭环 | ✅ |
| React 工作台（雷达/图谱/副驾） | ✅ |
| 演示案例 fixtures | ✅ 三案例 |
| Word/PDF 导出 / 信用报告 | ✅ |
| NL 加规则 · 本地 RAG · 担保链 KG（G6） | ✅ |
| 压力测试 · 多源冲突 · 五维归因 · 行业对标 | ✅ |
| 规则中心 / 报告中心独立页 | ✅ |
| AKShare Provider | ✅ 实现就绪（默认关闭） |

---

## 本地开发

本机若无全局 Python/Node，仓库可用 `.tools/` 下便携运行时（已 gitignore）。

```powershell
# API
$env:PYTHONPATH = "$PWD\packages;$PWD\apps"
.\.tools\python\python.exe -m uvicorn api.app.main:app --app-dir apps --host 127.0.0.1 --port 8000 --reload

# 或
.\scripts\dev.ps1 smoke
.\scripts\dev.ps1 test
.\scripts\dev.ps1 api

# Web（另开终端；把 .tools\node-v*-win-x64 加入 PATH）
cd apps\web
npm install
npm run dev
```

- Health: http://127.0.0.1:8000/v1/health  
- Web: http://127.0.0.1:5173（若占用则 Vite 会改用 5174）  
- 环境变量见 [`.env.example`](.env.example)；数据源占位 [`content/providers/registry.yaml`](content/providers/registry.yaml)

### 已跑通

- 种子规则 22 条 + 三案例 fixtures  
- `POST /v1/analyze`：规则命中 → 五维评分 → 等级 · 担保链图谱 · 指标溯源  
- **CSV / PDF / TXT 上传解析** → 入库指标 → 研判（并建本地 RAG 索引）  
  - CSV：`content/templates/metrics_template.csv`  
  - PDF/TXT：`content/templates/sample_financial_excerpt.pdf`  
- **ECharts 五维雷达 + AntV G6 担保链图谱**  
- **压力测试 / 多源冲突 / 五维归因 / 行业静态对标**（analyze 响应内嵌）  
- **规则中心** `/rules` · **报告中心** `/reports`  
- **一页摘要 / 信用评估报告**：`POST /v1/reports`（`confirm=true` 导出 MD + Word + PDF）  
- **NL 加规则**：`POST /v1/rules/from-nl`（pilot 入库，激活后参与计分）  
- **副驾 RAG**：`POST /v1/chat`（资料摘录问答；「加规则：…」分流）  
- **AKShare**：`POST /v1/providers/akshare/fetch`（需 `pip install akshare` 且 registry 启用）  
- **贷前尽调流程**：清单 → 研判 → 报告 → 人工确认提交  
- **演示脚本**：[`doc/15-demo-script.md`](doc/15-demo-script.md)

---

## 部署

BizAtlas 提供两种部署方式，产物均位于 [`deploy/`](deploy/)：

### 方式 A：容器化（推荐标准化环境）
见 [`deploy/README.md`](deploy/README.md) —— 基于 `deploy/Dockerfile`（`python:3.12-slim`）与 `deploy/docker-compose.yml`（`restart: unless-stopped` + 健康检查 + 数据卷）。

```bash
docker build -f deploy/Dockerfile -t bizatlas:0.3.0 .
docker run --rm -p 8000:8000 bizatlas:0.3.0
# 或 cd deploy && docker compose up --build
```

### 方式 B：生产服务器独立部署（systemd + nginx，无 Docker）
适用于裸机（如阿里云 ECS）。产物：
- [`deploy/bizatlas.service`](deploy/bizatlas.service) —— systemd 单元，`WorkingDirectory /opt/bizatlas`，`ExecStart` 跑 `python -m apps.api.launcher`，监听 `127.0.0.1:8000`。
- [`deploy/bizatlas_nginx.conf`](deploy/bizatlas_nginx.conf) —— nginx 站点，`listen 8080`，serve 前端 `dist` 并反代 `/v1` → `127.0.0.1:8000`（**SSE 已关 buffering**）。

典型落地（当前生产实例）：
- 服务器 `47.103.102.36`，部署目录 `/opt/bizatlas`，访问 `http://47.103.102.36:8080/`。
- Python ≥3.11（系统自带往往 <3.11，需另装 3.11 建 venv）；依赖 `pip install -r requirements.txt && pip install -e .`（editable 必装）。
- 默认 SQLite（`BIZATLAS_DB_PATH=./data/bizatlas.sqlite`），`BIZATLAS_AUTH_DISABLED=true`。
- 与 FastToken 等其他服务互不干扰（独立目录/端口）。
- ⚠️ 公网访问 8080 需在**阿里云安全组放行 8080 入站**。

> **命名说明**：本仓库 GitHub 即 [`MiLab-Bit/BizAtlas`](https://github.com/MiLab-Bit/BizAtlas)；产品 / 工程代号与 Python 包名均为 **BizAtlas / `bizatlas`**。（早期曾用名 GOPA，已弃用。）

---

*工程代号 BizAtlas · 产品名 商舆 · 文档对齐 PRD v1.0 · 2026-08-06*
