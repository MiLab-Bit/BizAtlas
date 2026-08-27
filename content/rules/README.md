# 规则资产目录

本目录为规则 source of truth（见 ADR-002）。

- 格式：YAML，Schema 对齐 PRD `05_规则与指标体系`
- MVP：`seed_*.yaml` 合计 ≥ 20 条（W1-5 填充）
- 运行时由 `packages/rules` 加载；`pilot` 规则只提示不计分

示例字段：

```yaml
- id: R1001
  name: 短期偿债能力红线
  dimension: 财务
  severity: 高
  condition:
    type: threshold
    metric: 流动比率
    op: "<"
    value: 1.0
  trigger: 提示+进评级
  version: 2026Q3
  status: active   # active | pilot | disabled
```
