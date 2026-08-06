# 05 · Agent 分析流水线

> 对齐 PRD：`03_核心功能` · `05_规则与指标体系` · `08_报告模板` · `04_交互流程`

---

## 1. 六阶段（Analyze Pipeline）

| 阶段 | 名称 | 输入 | 输出 | 主包 |
|---|---|---|---|---|
| S0 | Intent | 用户话术 / 按钮意图 | `Intent`（analyze_risk / gen_report / add_rule / ask） | orchestrator |
| S1 | Ingest | 文件 / URL / 已有 doc_id | `MetricPack` + chunks + 可选 KG 草案 | ingest, rag, kg |
| S2 | Enrich | MetricPack | 补全外部字段、质检、冲突列表 | data |
| S3 | Match | MetricPack + RuleSet | `RuleHits`（含 severity、explain） | rules |
| S4 | Score | MetricPack + RuleHits | `RiskResult`（五维、总分、等级、否决） | risk |
| S5 | Render | RiskResult + 模板 ID | `ReportDraft` + 一页摘要结构 | report |

流程辅助（贷前模板）在外层用 workflow 包裹 S1–S5，并增加「资料清单勾选」闸门。

---

## 2. 意图枚举（MVP）

| Intent | 触发例 | 管线 |
|---|---|---|
| `analyze_risk` | 「帮我看风险」 | S1–S4 + 摘要卡 |
| `gen_report` | 「生成信用评估报告」 | S1–S5（可复用缓存 RiskResult） |
| `ask_doc` | 「最大客户占比多少？」 | rag.qa → 引用回答 |
| `add_rule_nl` | 「商誉占比超 30% 预警」 | rules.nl_compile → pilot 入库 |
| `start_dd` | 「跑贷前尽调」 | workflow.due_diligence |

未知意图：澄清提问，不瞎跑全流程。

---

## 3. 规则匹配要点

- 规则源：`content/rules/*.yaml`，启动加载 + 热更新（mtime）。
- 类型：`threshold` | `trend` | `composite` | `event`。
- 命中输出必须含：`rule_id`, `metric_snapshot`, `severity`, `message`, `contribute_to_score`。
- NL 新增：LLM → Schema → 校验器 → `pilot` 标记（只提示不计分）→ 人工确认后转正。

种子规则：财务红线 + 失信/诉讼事件类，总数 ≥ 20（PRD 03-02 / 05）。

---

## 4. 风险评分要点

```
维度分 = Σ(指标危险度 × 指标权重) × 规则命中修正
总分   = Σ(维度分 × 维度权重)
等级   = f(总分) + 一票否决
```

维度权重（默认，可配置）：财务 30% · 经营 25% · 行业 15% · 舆情 15% · 关联 15%。

等级：GREEN 0–20 · YELLOW 20–40 · ORANGE 40–60 · RED 60–80 · BLACK 80–100。  
一票否决：失信被执行 / 破产重整 / 严重造假迹象 → BLACK。

压力测试（P1，框架 MVP 可留接口）：行业下行、大客户流失等情景 → 等级跳变说明。

---

## 5. 报告装配

模板 = 章节结构 + 插槽（数字/表/图/引用）。  
生成顺序：

1. 从 `RiskResult` / `MetricPack` **装填插槽**（确定性）。
2. LLM **仅润色**叙述段；若润色结果含未登记数字 → Gate 拒绝并回退模板句。
3. 人工复核 → 定稿 → 导出。

MVP 模板：

- 一页风险摘要（P0）
- 企业信用评估报告（P0）

见 PRD 08。

---

## 6. 结论先行（交互契约）

任何 `analyze_risk` / 报告摘要的首段必须是：

```text
一句话结论 + 风险等级
```

再展开：雷达、Top 风险点、依据链接。UI 与 API 字段 `summary.headline` / `summary.grade` 固定。

---

## 7. 错误与降级体验

| 情况 | 行为 |
|---|---|
| PDF 解析失败 | 提示上传 Excel 模板；任务状态 failed_partial |
| 仅部分指标可得 | 继续评分，缺失维度标注「数据不足」 |
| LLM 不可用 | 跳过润色与 NL 规则；核心评分/规则仍可用 |
| 外部 API 限流 | L2/L3，sources 表记日志 |

---

*下一步：[06-api-contracts.md](./06-api-contracts.md)*
