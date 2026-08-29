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

*工程代号 BizAtlas · 产品名 商舆 · 文档对齐 PRD v1.0 · 2026-08-06*

## 工程能力（为什么是商舆 BizAtlas）

> 本节汇总商舆在 **Agent 工程** 与 **数据工程** 两个方向上的真实积累。所有能力均已在仓库落地、可运行、可演示，不调黑箱、不编数字。

### 一、对 Agent 技术的理解（不只是调 LLM）

商舆把「金融分析师读资料 → 算风险 → 写报告」的过程，拆成一条 **可编排、可解释、可降级** 的 Agent 流水线，而不是把问题丢给一个大模型黑箱：

- **六阶段分析流水线（Analyze Pipeline）**：`S0 意图识别 → S1 资料理解 → S2 数据补全/质检 → S3 规则匹配 → S4 风险评分 → S5 报告装配`。每个阶段输入输出契约清晰（`Intent` / `MetricPack` / `RuleHits` / `RiskResult` / `ReportDraft`）。
- **意图驱动的任务图**：支持 `analyze_risk` / `gen_report` / `ask_doc` / `add_rule_nl` / `start_dd` 五类意图；未知意图先澄清，不盲目跑全流程。
- **人在回路（Human-in-the-loop）**：AI 出草稿与建议，人不确认不触发外部动作；NL 新增规则先入 `pilot`，人工确认后才转正计分。
- **LLM 的定位克制**：LLM 只做「解析辅助」与「文案润色」，关键数字与评分强制走确定性规则计算；润色结果若含未登记数字，Gate 直接拒绝并回退模板句——**关键数字零幻觉**。
- **编排层（Orchestrator）**：意图 → 任务图 → 人在回路闸门；流程辅助（贷前尽调）在外层用 workflow 包裹 S1–S5，并加「资料清单勾选」闸门。

### 二、数据工程能力（多源、降级、质检、溯源）

- **多源数据接入**：财务（上传 PDF/Excel 为主，可选 Tushare/AKShare）、工商、司法（诉讼/被执行/失信，一票否决演示）、公告、舆情、行业对标参数。AKShare Provider 已实现就绪（默认关闭）。
- **三级强制降级**：`L1 实时` → `L2 缓存（SQLite 上次成功值）` → `L3 估算（行业均值/历史外推，低置信度必须标注）`。每个字段携带 `tier / source / as_of / confidence` 元数据，**分析不得因单字段 L3 而中断**。
- **六维质检**：完整性、准确性（跨源冲突不自动裁定）、及时性、一致性（合并/母公司口径归一）、充足性、可用性追溯（缺引用则数字不得进报告正文）。质检结果进入 `QualityReport` 挂到分析响应。
- **本地 RAG + 担保链知识图谱（KG）**：文档切片检索做引用溯源问答；实体-关系图谱（G6 可视化）支撑关联风险与担保链推演。
- **SQLite 持久化**：companies / documents / document_chunks / financial_statements / financial_metrics / entities_relations / rules / rule_hits / risk_scores / reports 等表，支撑缓存、历史与溯源。
- **多源冲突与归因**：多源数据冲突进入冲突列表；五维评分支持归因到具体指标与规则命中；支持压力测试情景（行业下行、大客户流失）说明等级跳变。

### 三、风险研判内核

- **五维评分**：财务 30% · 经营 25% · 行业 15% · 舆情 15% · 关联 15%；`维度分 = Σ(指标危险度 × 指标权重) × 规则命中修正`。
- **GREEN–BLACK 五级**：0–20 / 20–40 / 40–60 / 60–80 / 80–100，叠加「失信被执行 / 破产重整 / 严重造假迹象」一票否决 → BLACK。
- **结论可溯源**：每条结论输出「数据 → 计算 → 结论」链路；报告首段固定为「一句话结论 + 风险等级」。

### 四、工程原则（不可砍）

1. **能力与领域分离**——算法内核通用，规则/模板外置可配置。
2. **可解释优先**——每条结论输出数据 → 计算 → 结论链路。
3. **人在回路**——AI 出草稿，人不确认不触发外部动作。
4. **降级不阻塞**——数据/服务不可用时继续跑，明确标注 `_tier`。
5. **关键数字零幻觉**——指标与评分强制走规则计算，LLM 不编数字。

### 五、已交付且可演示

API + 规则/风险闭环 · React 工作台（雷达 / 图谱 / 副驾）· 三套演示案例（健康 / 风险 / 违约）· Word/PDF 导出与信用评估报告 · NL 加规则 · 本地 RAG · 担保链 KG（G6）· 压力测试 · 多源冲突 · 五维归因 · 行业对标 · 规则中心 / 报告中心独立页 · AKShare Provider（默认关闭）。

### 技术栈

React + Vite（前端工作台） · FastAPI（后端） · SQLite（持久化与缓存） · YAML 规则库 · 本地 RAG / 知识图谱（G6） · 确定性规则引擎 + LLM 辅助。
