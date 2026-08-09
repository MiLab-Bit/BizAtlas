# 商舆 BizAtlas · 企业经营与风险研判 Agent

> **一次上传，一句提问，得到可解释、可溯源、可降级的企业风险研判。**

商舆（BizAtlas）面向「企业经营与风险研判」场景，把金融分析师"读资料 → 算风险 → 写报告"的繁重工作，压缩成一次资料上传、一句自然语言提问。它不做黑箱判断，而是让**关键数字走确定性计算、LLM 只做解析与文案、每一条结论都可溯源**。

- GitHub：https://github.com/MiLab-Bit/BizAtlas
- 产品 / 工程代号与 Python 包名：BizAtlas / `bizatlas`（早期曾用名 GOPA，已弃用）

---

## 一、产品介绍

在企业信贷、投资尽调、供应链风控等场景里，判断一家企业"经营是否健康、风险在哪里"，长期依赖分析师人工啃财报、查舆情、对规则——慢、贵、且难以复制。

商舆把这套研判能力工程化：你上传企业的财报 / 合同 / 舆情资料，或直接给出企业标识（股票代码、统一社会信用代码），商舆的**多智能体流水线**会自动完成资料理解、规则匹配、风险评分、归因与报告撰写，并始终把"数据 → 计算 → 结论"的链路摆在台面上。

它不追求"替代人"，而坚持**人在回路**：AI 产出草稿与建议，关键动作（导出正式报告、提交尽调结论）必须人工确认才生效。

---

## 二、使用网址

| 环境 | 地址 | 说明 |
|---|---|---|
| 生产环境（Web 工作台） | **http://47.103.102.36:8080/** | 前端 + API 一体部署。⚠️ 需阿里云安全组放行 `8080` 入站后，方可从公网访问；未放行时仅服务器本机可达。 |
| 本地开发（Web） | http://127.0.0.1:5173 | `npm run dev` 启动（端口被占用时 Vite 顺延） |
| 本地开发（API） | http://127.0.0.1:8000 | uvicorn，健康探针 `GET /v1/health` |

> API 核心端点：`POST /v1/analyze`（分析）、`POST /v1/reports`（报告导出）、`POST /v1/rules/from-nl`（自然语言加规则）、`POST /v1/chat`（副驾问答）、`GET /v1/analyze/pipeline/stream`（SSE 流式多智能体进度）、`GET /v1/health`（健康与数据源状态）。

---

## 三、品牌故事

**商舆**，取"商海舆情、商情全景"之意；**BizAtlas** 中 Atlas 是擎起地图与天穹的巨人——我们希望为每一家企业擎起一张**风险全景地图**。

市场上不缺"能聊天的 AI"，也不缺"能画图的 BI"。但当决策关系到真金白银的信贷与投资，**一句"这家公司靠谱吗"背后，是不能被幻觉辜负的数字**。商舆因此选择了一条更笨也更稳的路：

- 不让大模型编数字——评分、指标强制走规则引擎的确定性计算；
- 不让结论悬空——每个判断都附带数据来源与计算路径；
- 不让系统脆断——数据源挂了就降级，标注清楚再继续。

我们相信，AI 在企业金融里最该做的，不是"更像人地侃侃而谈"，而是"比人更稳地算清楚、讲明白"。商舆，就是这件事的工程化答卷。

---

## 四、核心功能

| 功能 | 说明 |
|---|---|
| **风险五维评分** | GREEN–BLACK 五档风险等级，覆盖偿债、盈利、运营、成长、合规等维度，分数由规则确定性计算。 |
| **担保链知识图谱** | 基于 AntV G6 绘制企业担保 / 关联网络，识别连环担保与风险传导路径。 |
| **指标溯源** | 每一个评分指标都可下钻到原始数据点："这条结论来自哪张表、哪条规则"。 |
| **压力测试 / 多源冲突 / 五维归因 / 行业对标** | 内置情景压力测试、多数据源冲突校验、归因分析、行业静态基准对标。 |
| **报告中心** | 一键生成「一页摘要」与「信用评估报告」，支持 Markdown / Word / PDF 导出（需人工确认 `confirm`）。 |
| **规则中心 + NL 加规则** | 外置 YAML 规则库（68 条已加载，含 22 条种子规则 + 三案例）；支持自然语言新增规则，激活后参与计分。 |
| **副驾 RAG** | `POST /v1/chat` 基于上传资料做本地检索问答；"加规则：…"可分流到规则中心。 |
| **贷前尽调流程** | 清单 → 研判 → 报告 → 人工确认提交，闭环贷前作业。 |
| **数据源状态面板** | 顶栏实时展示各数据源「就绪 / 异常 / 未启用」状态，系统健康一目了然。 |

---

## 五、我们和别的产品的不同（特性）

| 维度 | 通常的"AI 分析 / BI / 大模型" | 商舆 BizAtlas |
|---|---|---|
| **结论可信度** | 大模型直接给结论，数字可能是"编的" | 关键数字强制规则计算，**零幻觉**；LLM 仅做解析与文案 |
| **可解释性** | 黑箱，难说清"为什么" | 每条结论输出 **数据 → 计算 → 结论** 全链路，可溯源 |
| **人在回路** | 多直接自动执行 | AI 出草稿，**关键动作需人工确认**才生效（合规安全） |
| **数据韧性** | 单源或裸用，源挂即崩 | **三级降级**：主源失败切备用，再降级估算并标注 `_tier`，不阻塞 |
| **数据质量** | 入库即用 | **六维质检**：完整性 / 一致性 / 时效性 / 格式 / 异常 / 溯源 校验 |
| **数据主权** | 常上公有云大模型 | 上传资料建**本地 RAG 索引，数据不出域** |
| **领域可配置** | 改模型提示词 | 规则外置 + **自然语言加规则**，领域专家零代码增规则 |
| **架构** | 偏重单一对话 | 多智能体流水线（评分 / 分类 / 规划 / 研究），SSE 实时进度 |

---

## 六、数据：全，且经过验证

**接入全。** 商舆内置 **9 路数据接入，8 路已就绪**（企查查暂未启用）：

- 企业工商（天眼查）、行情（AKShare / Tushare）、公告与财报（cninfo 巨潮）、行业静态库、新闻舆情（AKShare）、企业 JSON 导入、资料上传、演示 fixture。

**验证严。** 数据不是"拿来就用"：

- **三级降级**：主数据源失败 → 自动切换备用源 → 再降级到静态库 / 估算值，并在结果中标注 `_tier`，让使用者清楚当前结论的置信来源。
- **六维质检**：入库前做完整性、一致性、时效性、格式、异常、溯源六项校验，脏数据不进研判。
- **本地 RAG + 溯源**：上传的 PDF / Excel 建本地检索索引，资料不离开本地；所有结论可回溯到具体数据点。
- **规则锚定**：68 条规则（22 条种子 + 三案例）作为判定基准，结论既来自数据，也来自可审计的规则，而非模型自由发挥。

---

## 七、目录与工程介绍

### 技术栈
- 后端：Python · FastAPI · SQLAlchemy / SQLite（可切托管 Postgres）
- 前端：React + Vite + TypeScript 工作台（雷达 / 图谱 / 副驾）
- 引擎：规则引擎 · 本地 RAG · 知识图谱（AntV G6）· 多智能体编排
- LLM：通义千问（Qwen，flash）

### 一句话架构
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

### 真实目录结构
```
BizAtlas/
├── README.md                 ← 本文件
├── pyproject.toml            ← 包定义（bizatlas）
├── requirements.txt
├── apps/
│   ├── api/                  ← FastAPI 服务（launcher.py 入口，监听 8000）
│   └── web/                  ← React + Vite 工作台（产物 dist/）
├── packages/bizatlas/        ← 引擎单体包
│   ├── agents/               ← 多智能体流水线（scoring/classifier/planner/researcher）
│   ├── orchestrator/         ← 编排层：意图 → 任务图 → 人在回路
│   ├── ingest/               ← 文档解析与指标抽取（PDF/Excel/TXT）
│   ├── data/                 ← 数据源适配 · 三级降级 · 六维质检（providers_*.py）
│   ├── rules/                ← 规则引擎（YAML 外置）
│   ├── risk/                 ← 五维评分 · 压力测试 · 归因
│   ├── rag/                  ← 本地检索（数据不出域）
│   ├── kg/                   ← 担保链知识图谱
│   ├── report/               ← 模板渲染与 Word/PDF 导出
│   ├── workflow/             ← 贷前尽调等流程模板
│   ├── llm/                  ← LLM 接入（Qwen）
│   ├── auth/                 ← RBAC 鉴权
│   ├── contracts/            ← 共享 Schema / 类型
│   └── industry/ identity/ evaluation/ service/ tools/ observability/ config.py
├── content/                  ← 外置资产：rules/ 规则库 · templates/ 报告模板 · fixtures/ 案例 · providers/registry.yaml
├── doc/                      ← 工程文档（架构 / 契约 / 前端 / 里程碑）
├── deploy/                   ← 部署产物（Dockerfile · compose · bizatlas.service · bizatlas_nginx.conf · README）
├── data/  uploads/  exports/ ← 运行时：SQLite / 上传 / 导出
├── scripts/                  ← 烟测 / 建库 / Spike
└── tests/                    ← pytest（154 passed）
```

### 工程原则（不可砍）
1. **能力与领域分离** — 算法内核通用；规则 / 模板外置可配置。
2. **可解释优先** — 每条结论输出「数据 → 计算 → 结论」链路。
3. **人在回路** — AI 出草稿与建议，人不确认不触发外部动作。
4. **降级不阻塞** — 数据 / 服务不可用时继续跑，明确标注 `_tier`。
5. **关键数字零幻觉** — 指标与评分强制走规则计算；LLM 不编数字。

### 本地开发
```powershell
# API
$env:PYTHONPATH = "$PWD\packages;$PWD\apps"
python -m uvicorn api.app.main:app --app-dir apps --host 127.0.0.1 --port 8000 --reload
# Web（另开终端）
cd apps\web && npm install && npm run dev
```
环境变量示例见 `.env.example`；数据源占位见 `content/providers/registry.yaml`。

### 部署
提供两种方式，详见 [`deploy/README.md`](deploy/README.md)：
- **容器化**：`deploy/Dockerfile`（`python:3.12-slim`）+ `deploy/docker-compose.yml`。
- **生产服务器独立部署（systemd + nginx）**：`deploy/bizatlas.service` + `deploy/bizatlas_nginx.conf`，监听 `8080`，反代 `/v1` 到 `8000`（SSE 已关 buffering）。当前生产实例：`47.103.102.36` → `/opt/bizatlas` → `http://47.103.102.36:8080/`。

### 文档入口
| 文档 | 内容 |
|---|---|
| [doc/README.md](doc/README.md) | 文档地图 |
| [doc/02-architecture.md](doc/02-architecture.md) | 分层、边界、主序列 |
| [doc/04-data-layer.md](doc/04-data-layer.md) | 数据源、降级、表结构 |
| [doc/05-agent-pipeline.md](doc/05-agent-pipeline.md) | 分析流水线六阶段 |
| [doc/06-api-contracts.md](doc/06-api-contracts.md) | HTTP 契约 |
| [doc/12-frontend-architecture.md](doc/12-frontend-architecture.md) | 工作台前端 |
| [deploy/README.md](deploy/README.md) | 部署运行手册 |

冲突时：**验收口径以产品设计（PRD）为准；实现细节以 `doc/` + ADR 为准。**

---

*商舆 BizAtlas · 企业经营与风险研判 Agent · 文档对齐 PRD v1.0 · 2026-08-09*
