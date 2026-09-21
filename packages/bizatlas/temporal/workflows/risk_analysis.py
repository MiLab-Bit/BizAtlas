"""RiskAnalysisWorkflow —— 多 Agent 研判管线（Temporal 底座）。

把原来的同步 `run_analysis_pipeline` / SSE `stream_analysis_pipeline` 迁移为可持久化、
可重试、可观测的 Temporal Workflow：

  评分内核(确定性, 唯一事实源)
    → 分类 → 规划(失败感知) → 研究(本地RAG) → 写作(writer-only)

每一步都是独立 Activity（重试/超时/心跳由 Temporal 托管）；Workflow 只做确定性编排，
并把每步的执行事件写入 self.progress，供 HTTP 网关通过 Query 轮询驱动 SSE。

确定性约束：Workflow 内不得直接调用 LLM / 读库 / 随机。所有"会变"的操作必须经
workflow.execute_activity 落到 Activity。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from bizatlas.temporal.activities import (
    build_trace_activity,
    classify_activity,
    plan_activity,
    research_activity,
    run_analyze_activity,
    write_activity,
)
from bizatlas.temporal.common import RiskAnalysisInput

# 时间线文案（与 stream.py 对齐，供前端渲染 Agent 卡）
_AGENT_LABELS: dict[str, str] = {
    "scoring": "风险评分内核",
    "classifier": "分类 Agent",
    "planner": "规划 Agent",
    "researcher": "研究 Agent",
    "writer": "写作 Agent",
}

# 默认 Activity 超时 / 重试
_ACT_TIMEOUT = timedelta(seconds=300)  # LLM 润色/研究较慢
_ACT_RETRY = RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ValueError"])


@workflow.defn(name="RiskAnalysisWorkflow")
class RiskAnalysisWorkflow:
    def __init__(self) -> None:
        self.progress: list[dict[str, Any]] = []
        self.status: str = "running"
        self.result: dict[str, Any] | None = None

    @workflow.run
    async def run(self, inp: RiskAnalysisInput) -> dict[str, Any]:
        self.progress.append({"type": "task_created", "company_id": inp.company_id})
        req_dict = {
            "company_id": inp.company_id,
            "intent": inp.intent,
            "template_id": inp.template_id,
            "options": inp.options,
        }

        # 1) 评分内核（确定性，唯一事实源）
        self._emit_start("scoring")
        core = await workflow.execute_activity(
            run_analyze_activity,
            req_dict,
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_ACT_RETRY,
        )
        risk = core.get("risk") or {}
        company = core.get("company") or {}
        metrics = core.get("metrics") or []
        self._emit_done(
            "scoring",
            True,
            "deterministic",
            f"等级 {risk.get('grade')} · 危险度 {risk.get('score')}",
        )

        # 2-5) 四个 Agent（顺序，后一步依赖前一步产出）
        cls_out = await self._run_agent("classifier", classify_activity, core)
        plan_out = await self._run_agent(
            "planner",
            plan_activity,
            {"risk": risk, "company": {**company, "metrics": metrics}, "classification": cls_out},
        )
        research_out = await self._run_agent(
            "researcher",
            research_activity,
            {
                "research_plan": (plan_out.get("output") or {}).get("research_plan") or [],
                "company_id": company.get("id"),
                "fixture_id": company.get("fixture_id"),
            },
        )
        writer_out = await self._run_agent(
            "writer",
            write_activity,
            {
                "risk": risk,
                "classification": cls_out,
                "planner": plan_out,
                "researcher": research_out,
                "company": company,
            },
        )

        # 汇总 Agent 信封（与 run_analysis_pipeline 同构）
        from bizatlas.agents.base import AgentMode

        agent_results = [cls_out, plan_out, research_out, writer_out]
        modes = [_mode_of(a) for a in agent_results]
        if any(m == AgentMode.LLM for m in modes):
            pipeline_mode = AgentMode.LLM.value
        elif any(m == AgentMode.FALLBACK for m in modes):
            pipeline_mode = AgentMode.FALLBACK.value
        else:
            pipeline_mode = AgentMode.DETERMINISTIC.value

        enriched: dict[str, Any] = dict(core)
        enriched.update(
            {
                "agents": {a.get("role"): a for a in agent_results},
                "classification": cls_out.get("output"),
                "data_gaps": (plan_out.get("output") or {}).get("data_gaps") or [],
                "research_findings": (researcher_out := research_out.get("output") or {}).get("findings") or [],
                "disclosures": (writer_out.get("output") or {}).get("disclosures") or [],
                "narrative": (writer_out.get("output") or {}).get("narrative") or {},
                "pipeline_mode": pipeline_mode,
                "pipeline_status": "succeeded",
            }
        )
        # 执行迹：CPU 密集型拼装下沉到 Activity（Workflow 只做编排），供前端回放
        trace = await workflow.execute_activity(
            build_trace_activity,
            enriched,
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_ACT_RETRY,
        )
        enriched["trace"] = trace
        self.result = enriched
        self.status = "completed"
        self.progress.append(
            {
                "type": "done",
                "trace": trace,
                "pipeline_mode": pipeline_mode,
                "pipeline_status": "succeeded",
            }
        )
        return enriched

    async def _run_agent(self, role: str, act: Any, arg: dict[str, Any]) -> dict[str, Any]:
        self._emit_start(role)
        out = await workflow.execute_activity(
            act, arg, start_to_close_timeout=_ACT_TIMEOUT, retry_policy=_ACT_RETRY
        )
        ok = bool(out.get("ok"))
        mode = out.get("mode")
        summary = self._agent_summary(role, out)
        self._emit_done(role, ok, mode, summary)
        return out

    # —— Queries（HTTP 网关轮询用）——
    @workflow.query
    def get_progress(self) -> list[dict[str, Any]]:
        return self.progress

    @workflow.query
    def get_status(self) -> str:
        return self.status

    @workflow.query
    def get_result(self) -> dict[str, Any] | None:
        return self.result

    # —— 内部辅助 ——
    def _emit_start(self, role: str) -> None:
        self.progress.append(
            {"type": "agent_start", "role": role, "label": _AGENT_LABELS.get(role, role)}
        )

    def _emit_done(self, role: str, ok: bool, mode: str | None, summary: str | None) -> None:
        self.progress.append(
            {
                "type": "agent_done",
                "role": role,
                "label": _AGENT_LABELS.get(role, role),
                "ok": ok,
                "mode": mode,
                "summary": summary,
            }
        )

    @staticmethod
    def _agent_summary(role: str, out: dict[str, Any]) -> str | None:
        if role == "classifier":
            return f"赛道 {(out.get('output') or {}).get('category')}"
        if role == "planner":
            gaps = (out.get("output") or {}).get("data_gaps") or []
            return f"发现 {len(gaps)} 项数据缺口"
        if role == "researcher":
            findings = (out.get("output") or {}).get("findings") or []
            found = [f for f in findings if f.get("found")]
            return f"命中 {len(found)} 维 · 缺口 {len(findings) - len(found)} 维"
        if role == "writer":
            disclosures = (out.get("output") or {}).get("disclosures") or []
            return f"透传 {len(disclosures)} 条披露"
        return None


def _mode_of(agent_dump: dict[str, Any]):
    """从 AgentResult dump 还原 AgentMode 枚举，用于汇总整条管线模式。"""
    from bizatlas.agents.base import AgentMode

    try:
        return AgentMode(agent_dump.get("mode"))
    except Exception:  # noqa: BLE001
        return AgentMode.DETERMINISTIC
