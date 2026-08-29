"""多 Agent 管线流式执行（SSE 用）。

与 run_analysis_pipeline 共享同一套子 Agent（run_analyze / classify / plan /
research / write）与 build_trace，仅以生成器方式逐步 yield 执行事件，便于前端
实时渲染 Agent 状态 / 事件时间线 / 画布节点（真正的"实时 SSE"，非事后派生）。

事件协议（每行一个 SSE data，JSON）：
- {"type":"task_created","company_id":...}
- {"type":"agent_start","role":...,"label":...}
- {"type":"agent_done","role":...,"label":...,"ok":bool,"mode":...,"summary":...}
- {"type":"done","trace":<build_trace 结果>,"pipeline_mode":...,"pipeline_status":"succeeded"}
"""

from __future__ import annotations

from typing import Any, Iterator

from bizatlas.agents.base import collect_agent_mode
from bizatlas.agents.classifier import classify_company
from bizatlas.agents.planner import plan_research
from bizatlas.agents.researcher import research
from bizatlas.agents.writer import write_report
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.orchestrator.trace import build_trace

_AGENT_LABELS: dict[str, str] = {
    "scoring": "风险评分内核",
    "classifier": "分类 Agent",
    "planner": "规划 Agent",
    "researcher": "研究 Agent",
    "writer": "写作 Agent",
}


def _split_target(company_id: str) -> tuple[str | None, str | None]:
    if company_id.startswith("fixture:"):
        return None, company_id.split(":", 1)[1]
    if company_id in {"healthy", "risky", "defaulted"}:
        return None, company_id
    return company_id, None


def stream_analysis_pipeline(req: AnalyzeRequest) -> Iterator[dict[str, Any]]:
    """逐步执行管线并 yield 执行事件（供 SSE）。零外部副作用，离线可用。"""
    from bizatlas.llm.client import set_force_deterministic

    opts = req.options or {}
    fast = bool(opts.get("fast") or opts.get("skip_polish"))
    # 快路径：整条管线强制确定性，避免 classifier/writer 再串行打 LLM
    set_force_deterministic(fast)
    try:
        yield {"type": "task_created", "company_id": req.company_id}

        # 1) 评分内核（确定性，唯一事实源）
        yield {"type": "agent_start", "role": "scoring", "label": _AGENT_LABELS["scoring"]}
        core = run_analyze(req)
        risk = core.get("risk") or {}
        company = core.get("company") or {}
        metrics = core.get("metrics") or []
        yield {
            "type": "agent_done",
            "role": "scoring",
            "label": _AGENT_LABELS["scoring"],
            "ok": True,
            "mode": "deterministic",
            "summary": f"等级 {risk.get('grade')} · 危险度 {risk.get('score')}",
        }

        # 2) 分类
        yield {"type": "agent_start", "role": "classifier", "label": _AGENT_LABELS["classifier"]}
        classification = classify_company(company, metrics)
        cls_out = classification.output or {}
        yield {
            "type": "agent_done",
            "role": "classifier",
            "label": _AGENT_LABELS["classifier"],
            "ok": bool(classification.ok),
            "mode": classification.mode.value,
            "summary": f"赛道 {cls_out.get('category')}",
        }

        # 3) 规划
        yield {"type": "agent_start", "role": "planner", "label": _AGENT_LABELS["planner"]}
        planner = plan_research(risk, {**company, "metrics": metrics}, classification.output)
        planner_out = planner.output or {}
        data_gaps = planner_out.get("data_gaps") or []
        yield {
            "type": "agent_done",
            "role": "planner",
            "label": _AGENT_LABELS["planner"],
            "ok": bool(planner.ok),
            "mode": planner.mode.value,
            "summary": f"发现 {len(data_gaps)} 项数据缺口",
        }

        # 4) 研究
        yield {"type": "agent_start", "role": "researcher", "label": _AGENT_LABELS["researcher"]}
        cid, fid = _split_target(req.company_id)
        researcher = research(planner_out.get("research_plan") or [], company_id=cid, fixture_id=fid)
        researcher_out = researcher.output or {}
        research_findings = researcher_out.get("findings") or []
        research_found = [f for f in research_findings if f.get("found")]
        yield {
            "type": "agent_done",
            "role": "researcher",
            "label": _AGENT_LABELS["researcher"],
            "ok": bool(researcher.ok),
            "mode": researcher.mode.value,
            "summary": f"命中 {len(research_found)} 维 · 缺口 {len(research_findings) - len(research_found)} 维",
        }

        # 5) 写作
        yield {"type": "agent_start", "role": "writer", "label": _AGENT_LABELS["writer"]}
        writer = write_report(risk, classification.output, planner.output, researcher.output, company)
        writer_out = writer.output or {}
        yield {
            "type": "agent_done",
            "role": "writer",
            "label": _AGENT_LABELS["writer"],
            "ok": bool(writer.ok),
            "mode": writer.mode.value,
            "summary": f"透传 {len(writer_out.get('disclosures') or [])} 条披露",
        }

        # 汇总（与 run_analysis_pipeline 同构）
        agent_results = [classification, planner, researcher, writer]
        pipeline_mode = collect_agent_mode(*agent_results).value
        enriched = dict(core)
        enriched.update(
            {
                "agents": {r.role: r.model_dump(mode="json") for r in agent_results},
                "classification": classification.output,
                "data_gaps": planner_out.get("data_gaps") or [],
                "research_findings": research_findings,
                "disclosures": writer_out.get("disclosures") or [],
                "narrative": writer_out.get("narrative") or {},
                "pipeline_mode": pipeline_mode,
                "pipeline_status": "succeeded",
            }
        )
        trace = build_trace(enriched)
        yield {
            "type": "done",
            "trace": trace,
            "pipeline_mode": pipeline_mode,
            "pipeline_status": "succeeded",
        }
    finally:
        set_force_deterministic(False)
