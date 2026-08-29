# 04 · 数据层设计

> 对齐 PRD：`06_数据源与数据层设计`

---

## 1. 数据分类与 MVP 优先级

| 类别 | 关键字段 | MVP 来源 | 优先级 |
|---|---|---|---|
| 财务 | 三表、派生指标 | 用户上传 PDF/Excel；可选 Tushare/AKShare | P0 |
| 工商 | 股权、法人、注册资本 | fixtures / 导出 JSON | P1（演示可 mock） |
| 司法 | 诉讼、被执行、失信 | fixtures / 导出 JSON | P0（一票否决演示） |
| 公告 | 全文 | 上传或巨潮（后续） | P1 |
| 舆情 | 新闻热度 | fixtures / 简单爬取 | P2 |
| 行业 | 增速、均值 | 静态行业参数表 | P0（对标用） |

财务免费主力：上传文件 > AKShare / Tushare。天眼查/企查查是工商司法补充，不是完整财务 API。

**接哪些 API、按功能如何排期：** 见 [11-data-apis.md](./11-data-apis.md)。

---

## 2. 三级降级（强制）

```
L1 实时：API / 本次上传解析成功
    ↓ 失败
L2 缓存：SQLite 上次成功值 + 时间戳
    ↓ 失败
L3 估算：行业均值 / 历史外推，置信度低，必须标注
```

每个字段携带元数据：

```json
{
  "metric": "流动比率",
  "value": 0.85,
  "unit": "ratio",
  "tier": "L1",
  "source": {"type": "document", "doc_id": "...", "page": 12},
  "as_of": "2024-12-31",
  "confidence": 0.95
}
```

分析流程**不得**因单字段 L3 而中断。

---

## 3. 六维质检

| 维度 | 检查 | 不合格动作 |
|---|---|---|
| 完整性 | 关键字段缺失率 | 提示补录 / 降级 |
| 准确性 | 跨源冲突 | 冲突列表，不自动裁定 |
| 及时性 | 报告期 / 抓取时间 | 过期标注 |
| 一致性 | 口径（合并/母公司） | 归一化或双轨标注 |
| 充足性 | 行业样本 | 「样本不足」 |
| 可用性追溯 | 来源与页码 | 缺引用则不可进报告正文数字 |

质检结果进入 `QualityReport`，挂到 `AnalyzeResponse`。

---

## 4. SQLite 表（MVP 最小集）

| 表 | 内容 |
|---|---|
| companies | 企业主数据 |
| documents | 上传文件元数据 |
| document_chunks | RAG 切片 |
| financial_statements | 三表原始/归一化行 |
| financial_metrics | 计算指标（含同环比） |
| entities_relations | 图谱节点与边 |
| rules | 规则库（亦可文件为源、DB 为运行缓存） |
| rule_hits | 命中记录 |
| risk_scores | 评分历史 |
| reports | 报告草稿与定稿 |
| alerts | 预警（流程用） |
| sources | 数据源与降级日志 |

路径默认：`BIZATLAS_DB_PATH=./data/bizatlas.sqlite`。

---

## 5. Provider 接口（可插拔）

```python
class DataProvider(Protocol):
    name: str
    def fetch(self, company_key: str, fields: list[str]) -> list[FieldValue]: ...
    def health(self) -> ProviderHealth: ...
```

MVP 实现：

| Provider | 职责 |
|---|---|
| `UploadFinancialProvider` | 解析结果写入 metrics |
| `AkshareProvider` / `TushareProvider` | 上市财务补充 |
| `FixtureProvider` | snapshot 模式 |
| `JsonImportProvider` | 天眼查/企查查导出 |

编排时由 `DataPlane.resolve(field)` 按模式选择 L1→L2→L3。

> 真实实现见 `packages/bizatlas/data/providers_*.py`（函数式 `fetch_*` 接口 + `registry.yaml` 驱动，无统一 Protocol 基类）。

---

## 6. 安全与合规（工程约束）

- 上传目录按 `company_id` 隔离；不跨租户共享。
- 日志避免落全文身份证等；法人/股东按最小化展示。
- 导出支持「脱敏」开关（隐藏敏感股东明细）。
- API Key 仅存环境变量，不进仓库。

---

*下一步：[05-agent-pipeline.md](./05-agent-pipeline.md)*
