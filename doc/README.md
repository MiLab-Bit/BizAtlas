# BizAtlas 工程文档索引

本目录是**工程落地文档**，回答「怎么建」。  
产品「建什么、为什么」见上级 [`../../`](../../)（`00`–`10` 产品设计模块）。

产品名 **商舆**（BizAtlas）。

---

## 阅读顺序（新人 / 开工）

| 顺序 | 文档 | 读完应知道 |
|---|---|---|
| 1 | [01-product-scope.md](./01-product-scope.md) | MVP 范围、Non-goals、不可砍需求 |
| 2 | [02-architecture.md](./02-architecture.md) | 分层架构、模块边界、主序列 |
| 3 | [03-tech-stack.md](./03-tech-stack.md) | 选型、Web3QuantMaster 复用映射 |
| 4 | [04-data-layer.md](./04-data-layer.md) | 数据源、三级降级、六维质检、表结构 |
| 5 | [05-agent-pipeline.md](./05-agent-pipeline.md) | 上传→研判→报告 六阶段流水线 |
| 6 | [06-api-contracts.md](./06-api-contracts.md) | HTTP 契约与核心 DTO |
| 7 | [11-data-apis.md](./11-data-apis.md) | 外部数据 API 接哪些、优先级 |
| 8 | [12-frontend-architecture.md](./12-frontend-architecture.md) | 雷达 Adopt、工作台/副驾、FSM |
| 9 | [09-directory-layout.md](./09-directory-layout.md) | 代码树与依赖方向 |
| 10 | [10-milestones.md](./10-milestones.md) | W1–W4 交付与验收 |
| 11 | [13-features-and-differentiators.md](./13-features-and-differentiators.md) | 五大功能与八大特色 |
| 12 | [15-demo-script.md](./15-demo-script.md) | 4–5 分钟演示口播 |

雷达完整清单副本：[reference/frontend-research-radar.md](./reference/frontend-research-radar.md)  
本地镜像研读：`c:\Dev\frontend-radar`

---

## ADR（架构决策）

| ADR | 主题 |
|---|---|
| [001](./adr/001-numbers-from-compute.md) | 关键数字强制走计算，LLM 不编数 |
| [002](./adr/002-rules-as-assets.md) | 规则与模板外置为版本化资产 |
| [003](./adr/003-degrade-not-block.md) | 三级降级，分析不中断 |
| [004](./adr/004-streamlit-mvp-ui.md) | 领域逻辑不进 UI（Streamlit 主路径已废止） |
| [005](./adr/005-react-workbench-ui.md) | React 工作台为正式前端 |

---

## 文档与 PRD 的关系

```
商舆漫游指南/00–10     →  需求、验收、口径（产品权威）
BizAtlas/doc/          →  架构、契约、实现约束（工程权威）
BizAtlas/apps|packages →  代码（实现）
```

冲突时：**验收口径以 PRD 为准；实现细节以本目录 ADR + 契约为准。**

---

## 产品设计对照表

| PRD 模块 | 工程文档 |
|---|---|
| 01 定位 · 09 MVP | [01-product-scope](./01-product-scope.md) |
| 07 技术架构 · 04 IA | [02-architecture](./02-architecture.md) · [03-tech-stack](./03-tech-stack.md) · [12-frontend](./12-frontend-architecture.md) |
| 06 数据架构 | [04-data-layer](./04-data-layer.md) |
| 03 五能力 · 04 IA | [05-agent-pipeline](./05-agent-pipeline.md) |
| 05 规则指标 · 08 报告 | ADR-001/002 · pipeline · contracts |
| 09 路线图 | [10-milestones](./10-milestones.md) |

---

*文档版本 v0.1 · 对齐 PRD v1.0 · 2026-08-06*
