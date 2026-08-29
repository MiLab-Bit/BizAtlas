# ADR-004 · 领域逻辑不进 UI（原 Streamlit MVP）

## 状态

**部分废止** · 2026-08-06  
「MVP 主 UI = Streamlit」已被 [ADR-005](./005-react-workbench-ui.md) 取代。  
下列条款**仍然有效**。

## 仍有效的决策

1. **所有业务逻辑经 FastAPI / orchestrator**；UI 不直连数据 Provider、不算风险分。  
2. 契约以 [`06-api-contracts.md`](../06-api-contracts.md) 为准，保证 UI 可替换。  
3. 人在回路操作必须显式确认后才调用受闸门保护的端点。

## 历史背景（归档）

初版为追求速度选择 Streamlit。引入前端雷达研读后，改为 React 工作台（ADR-005），以免 IA 与演示交互二次返工。
