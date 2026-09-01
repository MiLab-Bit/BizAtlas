# ADR-002 · 规则与模板外置为版本化资产

## 状态

已接受 · 2026-08-06

## 背景

PRD 要求规则可演化、可审计；能力内核与领域知识分离。

## 决策

1. 规则以 YAML 存放于 `content/rules/`，Schema 见 PRD 05。  
2. 报告模板定义于 `content/templates/`，与代码分离。  
3. 变更产生版本号；NL 新增默认 `pilot`（只提示不计分），人工 `activate` 后计入评分。  
4. 运行时可缓存入 SQLite，**文件仍为 source of truth**（MVP）。

## 后果

- 机构可在不改代码的情况下调阈值。  
- 需提供 schema 校验与加载失败时的明确报错。
