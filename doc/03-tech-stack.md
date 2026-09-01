# 03 · 技术选型与复用映射

> 对齐 PRD：`07_技术架构` §7.2–7.3

---

## 1. 选型表（Adopt）

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | **React + Vite** | 研究工作台 + 对话副驾；详见 [12-frontend-architecture](./12-frontend-architecture.md) · ADR-005 |
| 前端状态 | Zod · TanStack Query · Zustand · XState | 按雷达「状态所有权」分层，不镜像双真相 |
| 前端可视 | ECharts · TanStack Table ·（P1）G6 / xyflow | 雷达/趋势/指标表；图谱与流程后置 |
| 后端 | **Python FastAPI** | 与算法同语言；OpenAPI 自动文档 |
| LLM | OpenAI 兼容 API（可插拔） | 解析辅助 / NL 规则 / 报告润色；**不产出关键数字** |
| 检索 | 本地 RAG：TF-IDF + 可选向量 | 复用 Web3QuantMaster `rag_lookup` / `semantic_search` 思路 |
| 图谱 | **NetworkX** + JSON/Mermaid | MVP 不引 Neo4j |
| DB | **SQLite** 单文件 | 易私有化；后续可换 PostgreSQL |
| 文档解析 | pdfplumber / pypdf + openpyxl | 扫描件后续接 OCR；Excel 模板兜底 |
| 报告导出 | python-docx + reportlab/weasyprint | Word / PDF |
| 调度 | APScheduler（P2 贷后） | MVP 可手工触发 |
| 部署 | Docker 单机 | FastAPI + React 静态资源 + SQLite |

---

## 2. Web3QuantMaster → BizAtlas 映射

| 原能力 / 模块 | 复用方式 | BizAtlas 落点 | 改造点 |
|---|---|---|---|
| `rag_lookup` + `semantic_search` | 移植思路 / 可拷贝适配 | `packages/rag` | 知识库→企业资料切片 |
| `build_knowledge_graph` | 移植思路 | `packages/kg` | 实体→企业/人/机构/事件 |
| `risk_engine/`（VaR 等） | **计算内核思路** | `packages/risk` | 输入从价格序列→财务指标向量 |
| `risk_check`（校验/熔断） | 参考重写 | `packages/risk` + workflow | 对象→授信/监控阈值 |
| 压力测试框架 | 复用框架 | `packages/risk/stress` | 场景参数替换（见 PRD 05） |
| 归因引擎 | 复用思路 | Phase 2 | 收益归因→经营归因 |
| `signal_quality` | 评分逻辑 | `packages/risk/normalize` | 指标 0–100 危险度映射 |
| 三级降级 / 六维质检 | **原样保留模式** | `packages/data` | 源换成 Tushare/工商等 |
| MCP 工具编排 | 参考分类 | 后续 `tools/` 或 MCP server | 工具换成企业金融专用 |

> 原则：先落地「模式与接口」，再决定是拷贝源码还是重写。不以「依赖整个 Web3QuantMaster 仓库」为运行前提。

---

## 3. Python 包边界（建议）

```
packages/
  contracts/     # pydantic models，零业务依赖
  data/          # providers, cache, quality, db
  ingest/        # parsers, extractors
  rag/
  kg/
  rules/         # engine, nl_compiler
  risk/          # score, stress, veto
  report/        # templates binder, exporters
  workflow/      # templates FSM
  orchestrator/  # pipeline glue
```

依赖方向（硬约束）：

```
web → api (HTTP only)
api → orchestrator → {ingest, rules, risk, report, workflow}
orchestrator → data, rag, kg
report → contracts（RiskResult 等），↛ ingest 内部
rules ↛ risk（风险包消费命中结果，规则包不反向依赖评分）
* → contracts
```

---

## 4. 前端策略

- **正式 UI**：React 工作台（ADR-005），IA 对齐 PRD 04。
- **对话**：右侧 Copilot Panel → 只打 `/v1/chat` / `/v1/analyze`。
- **可视化**：ECharts 五维雷达；P1 用 G6 做担保链，失败降级邻接列表。
- **完整 Adopt 表与 Hold 清单**：见 [12-frontend-architecture](./12-frontend-architecture.md)。

---

## 5. 明确暂缓

| 技术 | 何时再议 |
|---|---|
| Neo4j / 图数据库 | 图谱规模与协同编辑有需求时 |
| Celery / Redis | 批量监测与长任务队列 |
| assistant-ui 整包 | 自研 Chat 不够用时（Trial） |
| 向量库（Milvus 等） | 本地 RAG 不够用时 |
| 天眼查实时 API | 有预算与 Key；此前用导出 JSON |

---

*下一步：[04-data-layer.md](./04-data-layer.md)*
