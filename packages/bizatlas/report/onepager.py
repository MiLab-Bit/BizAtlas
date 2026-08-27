from __future__ import annotations

from typing import Any

from bizatlas.report.titles import make_analysis_title


def build_onepager(
    *,
    company: dict[str, Any],
    risk: dict[str, Any],
    metrics_count: int,
) -> dict[str, Any]:
    """Assemble one-page risk summary slots from computed risk only (no LLM numbers)."""
    hits = risk.get("hits") or []
    top = hits[:5]
    dims = risk.get("dimensions") or []
    quality = risk.get("quality") or {}
    veto = risk.get("veto") or {}
    analysis_title = make_analysis_title(company, risk, "risk_onepager")

    return {
        "template_id": "risk_onepager",
        "title": "一页风险摘要",
        "analysis_title": analysis_title,
        "company": {
            "id": company.get("id"),
            "name": company.get("name"),
            "industry": company.get("industry"),
        },
        "headline": risk.get("headline"),
        "grade": risk.get("grade"),
        "score": risk.get("score"),
        "dimensions": dims,
        "top_risks": [
            {
                "rule_id": h.get("rule_id"),
                "severity": h.get("severity"),
                "message": h.get("message"),
                "explain": h.get("explain"),
            }
            for h in top
        ],
        "veto": veto,
        "data_quality": {
            "metrics_count": metrics_count,
            "completeness": quality.get("completeness"),
            "tier_mix": quality.get("tier_mix"),
        },
        "disclaimer": "关键数字来自抽取/规则计算；AI 未改写数值。本报告为辅助建议，不构成授信决策。",
    }


def render_onepager_markdown(payload: dict[str, Any]) -> str:
    company = payload.get("company") or {}
    lines = [
        f"# {payload.get('title', '一页风险摘要')}",
        "",
        f"**企业**：{company.get('name', '—')}　**行业**：{company.get('industry') or '—'}　"
        f"**等级**：{payload.get('grade')}　**得分**：{payload.get('score')}",
        "",
        f"> {payload.get('headline', '')}",
        "",
    ]
    if payload.get("narrative_lede"):
        lines.extend([payload["narrative_lede"], ""])
        if payload.get("narrative_polished"):
            lines.append("_（叙述经 AI 润色，已通过 Number Gate）_")
            lines.append("")
    lines.append("## 五维风险")
    for d in payload.get("dimensions") or []:
        lines.append(f"- {d.get('id')}: {d.get('score')}（权重 {d.get('weight')}）")

    lines.extend(["", "## Top 风险点"])
    tops = payload.get("top_risks") or []
    if not tops:
        lines.append("- 暂无规则命中")
    for i, h in enumerate(tops, 1):
        lines.append(
            f"{i}. [{h.get('severity')}] {h.get('message')} — {h.get('explain', '')} "
            f"(`{h.get('rule_id')}`)"
        )

    veto = payload.get("veto") or {}
    if veto.get("triggered"):
        lines.extend(["", f"**一票否决**：{veto.get('reason')}"])

    dq = payload.get("data_quality") or {}
    tier = dq.get("tier_mix") or {}
    lines.extend(
        [
            "",
            "## 数据说明",
            f"- 指标数：{dq.get('metrics_count')}",
            f"- 完整度：{dq.get('completeness')}",
            f"- 层级占比：L1 {tier.get('L1', 0)} / L2 {tier.get('L2', 0)} / L3 {tier.get('L3', 0)}",
            "",
            f"*{payload.get('disclaimer', '')}*",
            "",
        ]
    )
    return "\n".join(lines)
