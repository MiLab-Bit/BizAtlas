from __future__ import annotations

import json
import re
from typing import Any

from bizatlas.llm.client import LLMUnavailable, chat_completion, llm_configured
from bizatlas.llm.number_gate import collect_allowed_numbers, gate_or_fallback


def polish_narrative(
    *,
    role: str,
    facts_json: str,
    fallback: str,
    metrics: list[dict[str, Any]] | None = None,
    risk: dict[str, Any] | None = None,
    max_chars: int = 280,
) -> dict[str, Any]:
    """LLM polish a narrative; Number Gate rejects invented digits.

    Returns {text, polished, llm_used, gate_ok}.
    """
    base = (fallback or "").strip()
    if not llm_configured():
        return {"text": base, "polished": False, "llm_used": False, "gate_ok": True}

    allowed = collect_allowed_numbers(metrics=metrics, risk=risk)
    prompt = (
        f"你是 BizAtlas 报告写手。任务：{role}\n"
        "硬约束：只能使用【事实】里已有的数字与结论，禁止编造任何新数字、比例、日期。\n"
        f"输出纯中文叙述，不超过 {max_chars} 字，不要标题、不要列表符号。\n\n"
        f"【事实】\n{facts_json}\n\n"
        f"【模板原文（可改写语气，不可改数字）】\n{base}"
    )
    try:
        # 短超时：润色失败即回退模板，避免拖垮 /v1/analyze（GLM 首 token 偶发极慢）
        raw = chat_completion(
            [
                {"role": "system", "content": "你只润色叙述，不计算、不发明数字。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
            timeout=12.0,
        )
    except LLMUnavailable:
        return {"text": base, "polished": False, "llm_used": False, "gate_ok": True}

    text, accepted = gate_or_fallback(raw, base, allowed)
    return {
        "text": text,
        "polished": accepted and text != base,
        "llm_used": True,
        "gate_ok": accepted,
    }


def polish_report_sections(
    sections: list[dict[str, Any]],
    *,
    metrics: list[dict[str, Any]],
    risk: dict[str, Any],
) -> list[dict[str, Any]]:
    """Polish section body fields that are narrative (not bullet number dumps)."""
    narrative_ids = {"summary", "profile", "risk", "suggest"}
    out: list[dict[str, Any]] = []
    for sec in sections:
        item = dict(sec)
        if item.get("id") in narrative_ids and item.get("body"):
            facts = {
                "grade": risk.get("grade"),
                "score": risk.get("score"),
                "headline": risk.get("headline"),
                "section_id": item.get("id"),
                "title": item.get("title"),
                "bullets": item.get("bullets") or [],
            }
            polished = polish_narrative(
                role=f"润色报告章节「{item.get('title')}」的导语",
                facts_json=json.dumps(facts, ensure_ascii=False),
                fallback=str(item["body"]),
                metrics=metrics,
                risk=risk,
                max_chars=220,
            )
            item["body"] = polished["text"]
            item["body_polished"] = polished["polished"]
            item["body_gate_ok"] = polished["gate_ok"]
        out.append(item)
    return out


def polish_onepager_lede(
    payload: dict[str, Any],
    *,
    metrics: list[dict[str, Any]],
    risk: dict[str, Any],
) -> dict[str, Any]:
    """Add narrative_lede to onepager; keep headline numbers untouched."""
    out = dict(payload)
    facts = {
        "company": out.get("company"),
        "grade": out.get("grade"),
        "score": out.get("score"),
        "headline": out.get("headline"),
        "top_risks": out.get("top_risks") or [],
        "veto": out.get("veto") or {},
    }
    fallback = (
        f"{(out.get('company') or {}).get('name') or '该企业'}风险等级为 {out.get('grade')}，"
        f"综合危险度 {out.get('score')}。"
        f"{out.get('headline') or ''}"
    )
    polished = polish_narrative(
        role="写一页风险摘要的导语段（结论先行）",
        facts_json=json.dumps(facts, ensure_ascii=False),
        fallback=fallback,
        metrics=metrics,
        risk=risk,
        max_chars=240,
    )
    out["narrative_lede"] = polished["text"]
    out["narrative_polished"] = polished["polished"]
    out["narrative_gate_ok"] = polished["gate_ok"]
    if polished["polished"]:
        out["disclaimer"] = (
            "关键数字来自抽取/规则计算；叙述经 AI 润色且已通过 Number Gate。"
            "本报告为辅助建议，不构成授信决策。"
        )
    return out


def polish_headline(
    headline: str,
    *,
    metrics: list[dict[str, Any]],
    risk: dict[str, Any],
) -> dict[str, Any]:
    facts = {
        "grade": risk.get("grade"),
        "score": risk.get("score"),
        "hits": [
            {"severity": h.get("severity"), "message": h.get("message")}
            for h in (risk.get("hits") or [])[:5]
        ],
        "veto": risk.get("veto"),
        "template_headline": headline,
    }
    return polish_narrative(
        role="把风险结论改写成更顺口的一句话（保留等级含义与关键数字）",
        facts_json=json.dumps(facts, ensure_ascii=False),
        fallback=headline,
        metrics=metrics,
        risk=risk,
        max_chars=120,
    )


def explain_attribution_dim(
    dim: dict[str, Any],
    *,
    metrics: list[dict[str, Any]],
    risk: dict[str, Any],
) -> str:
    """Human explanation for one attribution dimension; empty if LLM off/fail."""
    if not llm_configured():
        return ""
    facts = {
        "dimension": dim.get("id"),
        "score": dim.get("score"),
        "weight": dim.get("weight"),
        "hits": dim.get("hits") or [],
        "drivers": dim.get("drivers") or [],
        "grade": risk.get("grade"),
        "total_score": risk.get("score"),
    }
    fallback = (
        f"{dim.get('id')}维度危险度 {dim.get('score')}，"
        f"命中 {(dim.get('hits') or []).__len__()} 条规则。"
    )
    polished = polish_narrative(
        role="用两到三句解释该风险维度为何得分（只翻译表格，不另算分）",
        facts_json=json.dumps(facts, ensure_ascii=False),
        fallback=fallback,
        metrics=metrics,
        risk=risk,
        max_chars=200,
    )
    return polished["text"] if polished["gate_ok"] else fallback


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def llm_json(prompt: str, *, temperature: float = 0.1) -> dict[str, Any] | None:
    if not llm_configured():
        return None
    try:
        raw = chat_completion(
            [
                {
                    "role": "system",
                    "content": "只输出合法 JSON 对象，不要 Markdown 代码围栏，不要解释。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=600,
        )
    except LLMUnavailable:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
