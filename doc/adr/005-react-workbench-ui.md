# ADR-005 · React 工作台为正式前端（取代 Streamlit 主路径）

## 状态

已接受 · 2026-08-06  
**取代** [ADR-004](./004-streamlit-mvp-ui.md) 中「MVP 主 UI = Streamlit」的结论；保留其「领域逻辑不进 UI、经 API」条款。

## 背景

1. PRD IA 需要：分栏工作台、结论先行风险页、溯源抽屉、对话副驾、规则表、报告确认闸门——Streamlit 可拼，但状态机与可替换性差。  
2. 完整前端雷达 + `c:\Dev\frontend-radar` 已具备 Zod / Query / XState / panels / ECharts / Table 等 Adopt 级镜像。  
3. 后端契约 [`06-api-contracts.md`](../06-api-contracts.md) 已按 HTTP 设计，UI 可并行。

## 决策

1. **正式 UI**：`apps/web` = **React + Vite**，架构见 [`12-frontend-architecture.md`](../12-frontend-architecture.md)。  
2. **领域逻辑仍只在 API / packages**；前端禁止直连 Tushare、禁止本地算风险分。  
3. Streamlit **降级为可选 Spike**（`scripts/` 或临时 `apps/web_spike`），不进入演示主路径，可不创建。  
4. 视觉与库选型以雷达 Adopt 表为准；Hold R3F、Docking、全量 AntD、粒子特效。

## 后果

- W1 需同时脚手架 API 与 Web；进度略高于「纯 Streamlit」，但避免 Phase 2 重写。  
- 演示质量、可解释交互（citation drawer、FSM 进度）明显更稳。  
- 需维护 TS Zod 与 Python Pydantic 对等（可由 JSON Schema 生成或手工同步关键 DTO）。
