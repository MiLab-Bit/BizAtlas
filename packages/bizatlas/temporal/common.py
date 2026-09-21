"""Temporal 跨边界数据类型（dataclass，避免依赖 pydantic 序列化器）。

Workfl/Activity 的所有入参/出参必须是 Temporal 默认 JSON DataConverter 可序列化的
类型：dataclass / dict / list / 基础类型。这里只放"跨边界"的结构体，领域结果统一用
dict（run_analyze 等已返回 dict）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskAnalysisInput:
    """多 Agent 研判管线的入参（对齐 AnalyzeRequest 的可序列化子集）。"""

    company_id: str
    intent: str = "analyze_risk"
    template_id: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    # 可选：指定 workflow id 以实现幂等启动（重复提交同 id 不会新建）
    workflow_id: str | None = None


@dataclass
class DueDiligenceInput:
    """贷前尽调 Workflow 的入参。"""

    company_id: str | None = None
    fixture_id: str | None = None
    name: str | None = None
    industry: str = ""


@dataclass
class AnalysisProgressEvent:
    """单条管线执行事件，对应 SSE 的 data 行（供前端实时渲染）。"""

    type: str  # task_created | agent_start | agent_done | done
    role: str | None = None
    label: str | None = None
    ok: bool | None = None
    mode: str | None = None
    summary: str | None = None
    trace: dict[str, Any] | None = None
    pipeline_mode: str | None = None
    pipeline_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        for k in ("role", "label", "ok", "mode", "summary", "trace", "pipeline_mode", "pipeline_status"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out
