# 10 · 里程碑与开发任务

> 对齐 PRD：`09_路线图与MVP`

---

## 1. 阶段总览

| 阶段 | 时间 | 工程目标 |
|---|---|---|
| Phase 0 | W0–W1 | Doc 冻结 · 脚手架 · 数据管线 Spike |
| Phase 1 MVP | W2–W4 | 五项能力闭环可演示 |
| Phase 2 | W5–W8 | 图谱 / 归因 / 对话增强 |
| Phase 3 | W9–W12 | 流程深化 · 批量监测 |
| Phase 4 | 12月+ | 私有化试点 |

当前完成：**Phase 0–1 MVP 可演示** + **Phase 2 差异化加分**（压力测试 / 冲突标注 / 五维归因 / G6 图谱 / 行业对标 / 规则·报告中心 / PDF）。

---

## 2. Phase 0 / W1 任务拆解

| ID | 任务 | 验收 |
|---|---|---|
| W1-0 | doc + README 冻结 | ✅ 本文档集 |
| W1-1 | `pyproject` + packages 空壳 + API hello | `GET /v1/health` 200 |
| W1-1b | `apps/web` Vite 壳 + Shell/分栏 + health 联调 | 打开工作台空白页可打通 API |
| W1-2 | SQLite schema + seed | 12 表可建 |
| W1-3 | PDF/Excel 解析 Spike | 10 份样例准确率基线报告 |
| W1-4 | Tushare/AKShare 或 FixtureProvider | hybrid/snapshot 可取数 |
| W1-5 | 种子规则 YAML ≥ 20 | 加载无 schema 错误 |

---

## 3. Phase 1 周里程碑

| 周 | 交付 | 验收 |
|---|---|---|
| W2 | 指标库 + 规则引擎 | 规则命中单测通过；NL→Schema 通路 |
| W3 | 风险评分 + 一页摘要 + 报告生成 | 3 标杆案例跑通 |
| W4 | React Copilot + 贷前流程 + Demo | 脚本全流程 < 5 分钟 |

---

## 4. 优先级（编码时）

| 优先级 | 事项 |
|---|---|
| P0 | 财报解析准确性 |
| P0 | 规则引擎可解释 |
| P0 | 报告生成（数字来自计算） |
| P1 | 知识图谱 · 压力测试 |
| P2 | 批量监测 · 行内集成 |

---

## 5. 风险应对（工程）

| 风险 | 应对 |
|---|---|
| 扫描件 PDF | OCR 后置；Excel 模板兜底 |
| 数据源限流 | snapshot fixtures + 三级降级 |
| LLM 幻觉 | ADR-001；Gate 拒未登记数字 |
| 时间紧 | 先保 P0 闭环，案例固定 |

---

## 6. 下一步行动（建议）

1. Review 本 `doc/` 与 PRD，确认无口径冲突。  
2. 开工 W1-1：脚手架 + health。  
3. 准备三案例 fixtures 目录结构与标注 JSON。

---

*文档版本 v0.1 · 2026-08-06*
