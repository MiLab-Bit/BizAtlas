"""写作 Agent：仅叙事发布（writer-only），**绝不**计算或修改风险评分。

职责边界：
- 输入是确定性评分结果（RiskResult）+ 规划缺口 + 检索发现，输出是叙事合成。
- 任何数字都必须来自 allowed set（Number Gate），LLM 若编造新数字则回退模板。
- 把上游的"失败感知"披露（数据缺口 / 检索缺失 / 否决项）原样透传到报告，
  让'缺数据'被看见而不是被润色掩盖。
"""

from __future__ import annotations

from typing import Any

from bizatlas.agents.base import AgentMode, AgentResult, Disclosure
from bizatlas.llm.number_gate import collect_allowed_numbers, extract_numbers
from bizatlas.llm.polish import polish_narrative


def _build_allowed(risk: dict[str, Any], findings: list[dict[str, Any]]) -> set[float]:
    allowed = collect_allowed_numbers(risk=risk)
    for f in findings:
        for n in extract_numbers(f.get("answer") or ""):
            allowed.add(n)
            if abs(n) <= 1.5:
                allowed.add(round(n * 100, 6))
    return allowed


def _section(
    *,
    role: str,
    base: str,
    risk: dict[str, Any],
    allowed: set[float],
    max_chars: int = 220,
) -> tuple[str, bool]:
    """生成一段叙事：优先 LLM 润色（过 Number Gate），失败回退模板 base。"""
    polished = polish_narrative(
        role=role,
        facts_json="",
        fallback=base,
        risk=risk,
        max_chars=max_chars,
    )
    return polished["text"], (polished["llm_used"] and polished["gate_ok"])


def write_report(
    risk: dict[str, Any],
    classification: dict[str, Any],
    planner_out: dict[str, Any],
    researcher_out: dict[str, Any],
    meta: dict[str, Any],
) -> AgentResult:
    name = meta.get("name") or "该企业"
    grade = risk.get("grade")
    score = risk.get("score")
    headline = risk.get("headline") or ""
    category = classification.get("category") or "other"
    segment = classification.get("segment") or ""

    allowed = _build_allowed(risk, researcher_out.get("findings") or [])

    # —— 执行摘要（结论先行）——
    exec_base = f"{name}（{segment or category}）风险等级{grade}，综合危险度{score}。{headline}"
    exec_summary, exec_llm = _section(
        role="写执行摘要（结论先行，不超过 80 字）",
        base=exec_base,
        risk=risk,
        allowed=allowed,
        max_chars=120,
    )

    # —— 风险叙事（来自确定性命中，不另算；去重避免同规则重复）——
    hits = risk.get("hits") or []
    if hits:
        seen_msgs: set[str] = set()
        ranked = sorted(
            hits,
            key=lambda h: {"高": 3, "中": 2, "低": 1}.get(h.get("severity"), 0),
            reverse=True,
        )
        unique: list[dict[str, Any]] = []
        for h in ranked:
            msg = h.get("message", "")
            if msg and msg not in seen_msgs:
                seen_msgs.add(msg)
                unique.append(h)
        top = unique[:3]
        risk_base = "主要风险点：" + "；".join(h.get("message", "") for h in top) + "。"
    else:
        risk_base = "暂无明显规则命中，结论以财务与定性指标为主，建议结合行业复核。"
    risk_narrative, risk_llm = _section(
        role="用两到三句解释风险成因（只翻译，不另算分）",
        base=risk_base,
        risk=risk,
        allowed=allowed,
    )

    # —— 检索合成 ——
    found = [f for f in (researcher_out.get("findings") or []) if f.get("found")]
    if found:
        research_base = (
            f"本地资料补充检索命中 {len(found)} 个维度；"
            + "；".join(f.get("answer", "")[:80] for f in found[:2] if f.get("answer"))
            + "。"
        )
    else:
        research_base = "本地资料未补充检索到额外信息，本报告以上传财务指标与规则研判为主。"
    research_synthesis, research_llm = _section(
        role="简要归纳本地资料检索发现（不引入新数字）",
        base=research_base,
        risk=risk,
        allowed=allowed,
    )

    # —— 建议 ——
    focus_dims = {h.get("dimension") for h in hits}
    if focus_dims:
        suggest_base = "建议重点核查：" + "、".join(sorted(focus_dims)) + " 维度，并补充对应佐证资料。"
    else:
        suggest_base = "建议补全核心财务指标与本地资料，以提升研判置信度。"
    recommendations, suggest_llm = _section(
        role="给出下一步核查建议（不编造数字）",
        base=suggest_base,
        risk=risk,
        allowed=allowed,
    )

    # —— 披露透传（失败感知）——
    disclosures: list[Disclosure] = []
    for g in planner_out.get("data_gaps") or []:
        disclosures.append(Disclosure(**g))
    for g in researcher_out.get("gap_disclosures") or []:
        disclosures.append(Disclosure(**g))
    veto = risk.get("veto") or {}
    if veto.get("triggered"):
        disclosures.append(
            Disclosure(
                code="veto",
                severity="warn",
                message=f"命中否决项：{veto.get('reason') or '重大风险'}，已直接判定为最高风险等级。",
            )
        )

    narrative = {
        "executive_summary": exec_summary,
        "risk_narrative": risk_narrative,
        "research_synthesis": research_synthesis,
        "recommendations": recommendations,
    }

    citations = researcher_out.get("citations") or []
    any_llm = any([exec_llm, risk_llm, research_llm, suggest_llm])
    mode = AgentMode.LLM if any_llm else AgentMode.DETERMINISTIC

    output = {
        "narrative": narrative,
        "disclosures": [d.model_dump() for d in disclosures],
        "citations": citations,
        "veto_disclosed": bool(veto.get("triggered")),
    }

    notes = []
    if mode == AgentMode.DETERMINISTIC:
        notes.append("未启用 LLM 或润色未通过 Number Gate，叙事采用确定性模板。")
    if disclosures:
        notes.append(f"报告含 {len(disclosures)} 条显式披露（数据/检索缺口）。")

    return AgentResult(
        role="writer",
        ok=True,
        mode=mode,
        output=output,
        citations=citations,
        notes=notes,
    )
