"""BizAtlas × Temporal 编排底座。

分层重构：把"多 Agent 研判管线"与"贷前尽调状态机"两类长任务/有状态流程迁移到
Temporal，FastAPI 退化为 HTTP 网关（start workflow / query / update / signal）。

包结构：
- client.py            懒连接的 Temporal Client 工厂
- common.py            跨边界 dataclass（RiskAnalysisInput / DueDiligenceInput / ...）
- activities.py        领域函数 → @activity.defn 封装（确定性/IO 逻辑）
- workflows/           Temporal Workflow 定义
    - risk_analysis.py   多 Agent 管线（评分内核 → 分类 → 规划 → 研究 → 写作）
    - due_diligence.py   贷前尽调状态机（Update 驱动 + 人在回路）
- worker.py            Worker 启动器（注册 Workflow/Activity）

启用开关见 config.BIZATLAS_TEMPORAL_ENABLED；默认关闭，关闭时 API 走原有同步路径。
"""

from __future__ import annotations
