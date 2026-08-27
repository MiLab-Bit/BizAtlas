"""多 Agent 编排流水线。

顺序：分类 → 规划（失败感知）→ 确定性评分内核（run_analyze，唯一事实源）
      → 研究（本地 RAG 检索）→ 写作（writer-only 叙事发布）。

关键约束：
- run_analyze 的 rating 结果（grade/score/risk）**原样透传**，任何 Agent 不得改分；
  writer 只在其之上叠加叙事与披露。
- 全程离线可用：无 LLM 时各 Agent 走确定性/模板降级。
"""

from __future__ import annotations

from typing import Any

from bizatlas.agents.base import AgentMode, AgentResult, collect_agent_mode
from bizatlas.agents.classifier import classify_company
from bizatlas.agents.planner import plan_research
from bizatlas.agents.researcher import research
from bizatlas.agents.writer import write_report
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.orchestrator.analyze import run_analyze


def _split_target(company_id: str) -> tuple[str | None, str | None]:
    """解析真实 company_id 与 fixture_id（供 RAG 检索）。"""
    if company_id.startswith("fixture:"):
        return None, company_id.split(":", 1)[1]
    if company_id in {"healthy", "risky", "defaulted"}:
        return None, company_id
    return company_id, None


def run_analysis_pipeline(req: AnalyzeRequest) -> dict[str, Any]:
    # 1) 确定性评分内核（唯一事实源）
    core = run_analyze(req)
    risk = core.get("risk") or {}
    company = core.get("company") or {}
    metrics = core.get("metrics") or []

    # 2) 分类
    classification = classify_company(company, metrics)

    # 3) 规划（失败感知）
    planner = plan_research(
        risk,
        {**company, "metrics": metrics},
        classification.output,
    )

    # 4) 研究（本地 RAG 检索）
    cid, fid = _split_target(req.company_id)
    researcher = research(
        planner.output.get("research_plan") or [],
        company_id=cid,
        fixture_id=fid,
    )

    # 5) 写作（writer-only）
    writer = write_report(
        risk,
        classification.output,
        planner.output,
        researcher.output,
        company,
    )

    # 汇总 Agent 信封
    agent_results = [classification, planner, researcher, writer]
    pipeline_mode = collect_agent_mode(*agent_results).value

    enriched = dict(core)
    enriched.update(
        {
            "agents": {
                r.role: r.model_dump(mode="json") for r in agent_results
            },
            "classification": classification.output,
            "data_gaps": planner.output.get("data_gaps") or [],
            "research_findings": researcher.output.get("findings") or [],
            "disclosures": writer.output.get("disclosures") or [],
            "narrative": writer.output.get("narrative") or {},
            "pipeline_mode": pipeline_mode,
            "pipeline_status": "succeeded",
        }
    )
    return enriched
