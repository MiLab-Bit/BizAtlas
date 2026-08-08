"""规划 Agent：基于确定性评分结果与分类，产出研究计划与**数据缺口清单**。

这是"失败感知"的核心：在结论生成之前，先把系统"不知道/不完整"之处
显式枚举出来（缺指标、低置信数据、证据不足维度），而不是默默用估算填补。
"""

from __future__ import annotations

from typing import Any

from bizatlas.agents.base import AgentMode, AgentResult, Disclosure

# 一份完整研判期望覆盖的 8 项核心财务指标（对齐 score.py 完整度分母）
_EXPECTED_METRICS: list[str] = [
    "流动比率",
    "速动比率",
    "资产负债率",
    "净资产收益率",
    "毛利率",
    "净利率",
    "营业收入增长率",
    "经营现金流量净额",
]

# 维度 → 对应本地资料检索提问（供 Researcher 执行；检索为空即触发缺口披露）
_DIMENSION_QUERIES: dict[str, str] = {
    "财务": "财报审计意见、债务到期结构与偿债压力",
    "经营": "主营业务稳定性、上下游集中度与产能利用",
    "行业": "所处行业周期、政策导向与竞争格局",
    "舆情": "近一年负面新闻、监管处罚与重大投诉",
    "关联": "对外担保、关联资金往来与股权质押",
}


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def plan_research(
    risk: dict[str, Any],
    meta: dict[str, Any],
    classification: dict[str, Any],
) -> AgentResult:
    gaps: list[Disclosure] = []
    notes: list[str] = []

    metrics = meta.get("_metrics") or []
    metric_names = {_norm(m.get("name", "")) for m in metrics}
    # 也考虑 pipeline 直接传入的 metrics dump（位于 risk 之外的顶层）
    top_metrics = (meta.get("metrics") or []) if isinstance(meta.get("metrics"), list) else []
    metric_names |= {_norm(m.get("name", "")) for m in top_metrics}

    # 1) 缺失核心指标
    missing = [m for m in _EXPECTED_METRICS if _norm(m) not in metric_names]
    if missing:
        gaps.append(
            Disclosure(
                code="missing_metrics",
                severity="warn",
                message=f"缺少关键财务指标：{ '、'.join(missing) }，相关维度只能依赖有限数据或估算。",
            )
        )

    # 2) 资料完整度
    quality = risk.get("quality") or {}
    completeness = quality.get("completeness")
    if completeness is not None and completeness < 1.0:
        gaps.append(
            Disclosure(
                code="low_completeness",
                severity="warn",
                message=f"资料完整度仅 {completeness}，部分维度数据不足，结论置信度相应下调。",
            )
        )

    # 3) 低置信 / 估算数据
    tier_mix = quality.get("tier_mix") or {}
    est_share = (tier_mix.get("L3") or 0.0)
    if est_share > 0:
        gaps.append(
            Disclosure(
                code="estimate_tier",
                severity="info",
                message=f"约 {round(est_share * 100)}% 指标来自估算/低置信来源（L3），结论需谨慎采信。",
            )
        )

    # 4) 证据不足维度
    hits = risk.get("hits") or []
    dim_evidence: dict[str, int] = {}
    for h in hits:
        dim = h.get("dimension") or "财务"
        dim_evidence[dim] = dim_evidence.get(dim, 0) + len(h.get("evidence_refs") or [])
    dimensions = risk.get("dimensions") or []
    for d in dimensions:
        dim_id = d.get("id")
        if dim_evidence.get(dim_id, 0) == 0 and (d.get("score") or 0) > 0:
            gaps.append(
                Disclosure(
                    code="weak_evidence",
                    severity="info",
                    message=f"「{dim_id}」维度得分 {d.get('score')} 但缺乏直接证据支撑，建议补充佐证。",
                )
            )

    # 5) 数据冲突
    conflicts = quality.get("conflicts") or 0
    if conflicts and conflicts > 0:
        gaps.append(
            Disclosure(
                code="data_conflicts",
                severity="warn",
                message=f"检测到 {conflicts} 处指标数据冲突，已按规则处理，建议人工复核原始资料。",
            )
        )

    # 检索计划：依据分类路由 + 五维，生成可执行的本地检索提问
    routing = classification.get("routing_hints") or ["财务", "经营", "行业", "舆情", "关联"]
    name = meta.get("name") or "该企业"
    research_plan: list[dict[str, str]] = []
    for dim in routing:
        q = _DIMENSION_QUERIES.get(dim, f"{dim}相关风险信息")
        research_plan.append({"dimension": dim, "query": f"查询 {name} 的{q}"})

    focus = "、".join(routing[:3])
    output = {
        "research_plan": research_plan,
        "data_gaps": [g.model_dump() for g in gaps],
        "focus": focus,
        "missing_metrics": missing,
    }

    return AgentResult(
        role="planner",
        ok=True,
        mode=AgentMode.DETERMINISTIC,
        output=output,
        notes=notes,
    )
