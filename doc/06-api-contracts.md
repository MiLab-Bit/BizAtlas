# 06 · API 契约（MVP）

> 实现以 Pydantic 模型为准；本文件是契约说明书。  
> 前缀：`/v1` · JSON · UTF-8

---

## 1. 通用约定

### 响应包络

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "meta": {
    "request_id": "uuid",
    "mode": "hybrid",
    "degraded": false
  }
}
```

失败时 `ok=false`，`error.code` / `error.message` 可读。

### 核心枚举

- `RiskGrade`: `GREEN` | `YELLOW` | `ORANGE` | `RED` | `BLACK`
- `DataTier`: `L1` | `L2` | `L3`
- `TaskStatus`: `queued` | `running` | `succeeded` | `failed` | `failed_partial` | `awaiting_human`

---

## 2. 端点清单

| Method | Path | 说明 |
|---|---|---|
| GET | `/v1/health` | 存活 + 模式 + provider 健康 |
| POST | `/v1/companies` | 创建企业空间 |
| GET | `/v1/companies/{id}` | 企业概要 |
| POST | `/v1/companies/{id}/documents` | 上传资料（multipart） |
| GET | `/v1/companies/{id}/documents` | 资料列表与解析状态 |
| POST | `/v1/analyze` | 启动分析（风险/报告） |
| GET | `/v1/analyze/{task_id}` | 任务状态与结果 |
| GET | `/v1/companies/{id}/risk/latest` | 最新 RiskResult |
| GET | `/v1/rules` | 规则列表 |
| POST | `/v1/rules/from-nl` | NL 新增（默认 pilot） |
| POST | `/v1/rules/{id}/activate` | 人工确认转正 |
| POST | `/v1/reports` | 基于已有分析结果生成报告 |
| POST | `/v1/reports/{id}/export` | 导出 Word/PDF（需确认） |
| POST | `/v1/chat` | 对话入口（意图路由） |
| POST | `/v1/workflows/due-diligence` | 启动贷前流程 |
| GET | `/v1/workflows/{id}` | 流程状态 |

---

## 3. 关键 DTO（摘要）

### MetricValue

```yaml
name: string           # 流动比率
value: number | null
unit: string
tier: L1|L2|L3
as_of: date
source:
  type: document|api|cache|estimate
  ref: string          # doc_id or provider
  page: int | null
confidence: number     # 0–1
```

### RuleHit

```yaml
rule_id: string
name: string
dimension: string
severity: high|medium|low
message: string
metrics: MetricValue[]
contribute_to_score: bool
explain: string        # 人可读：条件与实际值
```

### RiskResult

```yaml
company_id: string
grade: RiskGrade
score: number          # 0–100
headline: string       # 一句话结论
dimensions:
  - id: financial|operating|industry|sentiment|related
    score: number
    weight: number
hits: RuleHit[]
veto: { triggered: bool, reason: string | null }
quality: { completeness: number, conflicts: int, tier_mix: object }
computed_at: datetime
```

### AnalyzeRequest

```yaml
company_id: string
intent: analyze_risk|gen_report|ask_doc|start_dd
message: string | null
document_ids: string[] | null   # 空则用企业下全部已解析
template_id: string | null      # gen_report 时
options:
  include_stress: bool          # 默认 false（P1）
  include_kg: bool              # 默认 false（P1）
```

### AnalyzeResponse.data

```yaml
task_id: string
status: TaskStatus
summary:
  headline: string
  grade: RiskGrade
  score: number
risk: RiskResult | null
report_id: string | null
citations: { id: string, label: string }[]
```

---

## 4. 人在回路闸门

下列操作要求 `confirm=true`（或等价头/字段），否则 409：

- `POST /v1/reports/{id}/export`
- `POST /v1/rules/{id}/activate`
- 流程「提交评审」类动作

---

## 5. 错误码（节选）

| code | 含义 |
|---|---|
| `DOC_PARSE_FAILED` | 解析失败，建议 Excel 兜底 |
| `INSUFFICIENT_METRICS` | 关键指标过少，结果降级 |
| `LLM_UNAVAILABLE` | 润色/NL 不可用，核心仍可能成功 |
| `HUMAN_CONFIRM_REQUIRED` | 需要确认 |
| `RULE_SCHEMA_INVALID` | NL 编译未通过校验 |

---

*下一步：[09-directory-layout.md](./09-directory-layout.md)*
