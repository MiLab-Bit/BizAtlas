from __future__ import annotations

import json
from typing import Any

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data import repo
from bizatlas.data.providers_tianyancha import fetch_company_profile, tianyancha_configured
from bizatlas.ingest.fixtures import list_fixtures, load_fixture_company
from bizatlas.llm.client import LLMUnavailable, chat_completion, llm_configured
from bizatlas.llm.number_gate import collect_allowed_numbers, gate_or_fallback
from bizatlas.orchestrator.analyze import run_analyze


def _match_fixture(company_name: str) -> str | None:
    """可选：本地案例名完全匹配时附带财务管线，不作为产品演示入口。"""
    name = (company_name or "").strip()
    if not name:
        return None
    for fid in list_fixtures():
        try:
            data = load_fixture_company(fid)
        except FileNotFoundError:
            continue
        fname = str(data.get("name") or "")
        if name == fname:
            return fid
    return None


def start_background_session(company_name: str, *, industry: str = "") -> dict[str, Any]:
    """创建企业会话：优先拉天眼查，再开 LLM 背调。"""
    name = (company_name or "").strip()
    if not name:
        raise ValueError("请输入企业名称")

    fixture_id = _match_fixture(name)
    analyze_summary = None
    tyc: dict[str, Any] | None = None

    company = repo.create_company(name, industry)
    company_id = company["id"]
    display_name = name

    if tianyancha_configured():
        try:
            tyc = fetch_company_profile(name)
            if tyc.get("ok") and (tyc.get("basic") or {}).get("name"):
                display_name = str(tyc["basic"]["name"])
                # update stored name to canonical
                repo.ensure_company(company_id, display_name, industry or "")
        except Exception as exc:  # noqa: BLE001
            tyc = {"ok": False, "source": "tianyancha", "message": str(exc)}

    if fixture_id:
        data = load_fixture_company(fixture_id)
        metrics = data.get("_metrics") or []
        if metrics:
            repo.replace_metrics(company_id, metrics)
        try:
            result = run_analyze(
                AnalyzeRequest(
                    company_id=fixture_id,
                    intent="analyze_risk",
                    options={"include_stress": False, "include_kg": True},
                )
            )
            analyze_summary = result.get("summary")
        except Exception:  # noqa: BLE001
            analyze_summary = None

    opener = background_reply(
        "请对该企业做信用背调开场：结论先行，并结合工商/司法事实说明要点。",
        company_id=company_id,
        company_name=display_name,
        fixture_id=fixture_id,
        tyc_profile=tyc,
    )
    return {
        "company_id": company_id,
        "company_name": display_name,
        "fixture_id": fixture_id,
        "matched_fixture": fixture_id is not None,
        "tianyancha": {
            "ok": bool(tyc and tyc.get("ok")),
            "configured": tianyancha_configured(),
            "message": (tyc or {}).get("message"),
        },
        "summary": analyze_summary,
        "message": opener.get("answer"),
        "llm_used": opener.get("llm_used"),
        "gate_ok": opener.get("gate_ok"),
    }


def background_reply(
    message: str,
    *,
    company_id: str | None,
    company_name: str,
    fixture_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    tyc_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LLM 背调：事实来自天眼查 + 本地管线；禁止编造未出现的数字。"""
    msg = (message or "").strip()
    if not msg:
        raise ValueError("消息为空")

    facts: dict[str, Any] = {
        "company_name": company_name,
        "company_id": company_id,
        "has_computed_risk": False,
        "tianyancha": None,
    }
    metrics_dump: list[dict[str, Any]] = []
    risk_dump: dict[str, Any] = {}

    # 每次对话尽量带上最新工商快照（有 token 时）
    if tyc_profile is not None:
        facts["tianyancha"] = tyc_profile
    elif tianyancha_configured():
        try:
            facts["tianyancha"] = fetch_company_profile(company_name)
        except Exception as exc:  # noqa: BLE001
            facts["tianyancha"] = {"ok": False, "message": str(exc)}

    target = fixture_id or company_id
    if target:
        try:
            result = run_analyze(
                AnalyzeRequest(
                    company_id=str(target),
                    intent="analyze_risk",
                    options={"include_stress": False, "include_kg": False},
                )
            )
            facts["has_computed_risk"] = True
            facts["summary"] = result.get("summary")
            facts["risk"] = {
                "grade": (result.get("risk") or {}).get("grade"),
                "score": (result.get("risk") or {}).get("score"),
                "headline": (result.get("risk") or {}).get("headline"),
                "hits": [
                    {
                        "severity": h.get("severity"),
                        "message": h.get("message"),
                        "rule_id": h.get("rule_id"),
                    }
                    for h in ((result.get("risk") or {}).get("hits") or [])[:8]
                ],
                "veto": (result.get("risk") or {}).get("veto"),
            }
            metrics_dump = result.get("metrics") or []
            facts["metrics"] = [
                {"name": m.get("name"), "value": m.get("value"), "tier": m.get("tier")}
                for m in metrics_dump[:24]
            ]
            risk_dump = result.get("risk") or {}
        except Exception:  # noqa: BLE001
            if company_id:
                try:
                    metrics = repo.load_metrics(company_id)
                    metrics_dump = [m.model_dump(mode="json") for m in metrics]
                    facts["metrics"] = [
                        {"name": m.get("name"), "value": m.get("value"), "tier": m.get("tier")}
                        for m in metrics_dump[:24]
                    ]
                except Exception:  # noqa: BLE001
                    pass

    tyc_ok = bool((facts.get("tianyancha") or {}).get("ok"))
    fallback_bits = [f"关于「{company_name}」："]
    if tyc_ok:
        basic = (facts["tianyancha"] or {}).get("basic") or {}
        fallback_bits.append(
            f"工商状态 {basic.get('regStatus') or '—'}，"
            f"法定代表人 {basic.get('legalPerson') or '—'}，"
            f"注册资本 {basic.get('regCapital') or '—'}。"
        )
        dish = (facts["tianyancha"] or {}).get("dishonest") or {}
        if dish.get("count"):
            fallback_bits.append(f"失信记录约 {dish.get('count')} 条，需人工复核。")
    elif facts.get("has_computed_risk"):
        fallback_bits.append(
            f"本地风险等级 {facts.get('summary', {}).get('grade')}，"
            f"危险度 {facts.get('summary', {}).get('score')}。"
            f"{facts.get('summary', {}).get('headline') or ''}"
        )
    else:
        fallback_bits.append("已受理背调请求；工商/财务事实仍在补全中，请继续追问关注点。")
    fallback = "".join(fallback_bits)

    if not llm_configured():
        return {
            "answer": fallback,
            "llm_used": False,
            "gate_ok": True,
            "facts": {
                "has_computed_risk": facts.get("has_computed_risk"),
                "tianyancha_ok": tyc_ok,
            },
        }

    system = (
        "你是 BizAtlas 企业信用背调助手。用简洁专业中文对话。\n"
        "硬约束：\n"
        "1) 只能使用【事实】中的工商/司法/财务字段与数字，禁止编造营收、利润、诉讼金额。\n"
        "2) 事实来自天眼查或本地计算管线；缺失处写「待核验」，不要假装已全库查完。\n"
        "3) 结论先行：先一句话判断，再分点。\n"
        "4) 少用 Markdown 标题符号。"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in (history or [])[-8:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": str(content)})
    messages.append(
        {
            "role": "user",
            "content": f"【事实】\n{json.dumps(facts, ensure_ascii=False)}\n\n【用户】\n{msg}",
        }
    )

    try:
        raw = chat_completion(messages, temperature=0.25, max_tokens=900)
    except LLMUnavailable:
        note = "（叙述模型暂不可用，以上为天眼查/本地事实摘要，可继续追问。）" if tyc_ok else ""
        return {
            "answer": f"{fallback}{note}",
            "llm_used": False,
            "gate_ok": True,
            "facts": {"has_computed_risk": facts.get("has_computed_risk"), "tianyancha_ok": tyc_ok},
        }

    # 天眼查文本字段里的数字也放行（注册资本等）
    extra_nums: list[float] = []
    basic = ((facts.get("tianyancha") or {}).get("basic") or {})
    for key in ("regCapital",):
        val = basic.get(key)
        if isinstance(val, (int, float)):
            extra_nums.append(float(val))
        elif isinstance(val, str):
            import re

            for m in re.findall(r"\d+(?:\.\d+)?", val):
                try:
                    extra_nums.append(float(m))
                except ValueError:
                    pass
    dish = (facts.get("tianyancha") or {}).get("dishonest") or {}
    if dish.get("count") is not None:
        try:
            extra_nums.append(float(dish["count"]))
        except (TypeError, ValueError):
            pass

    allowed = collect_allowed_numbers(metrics=metrics_dump, risk=risk_dump, extra=extra_nums)
    text, ok = gate_or_fallback(raw, fallback, allowed)
    return {
        "answer": text,
        "llm_used": True,
        "gate_ok": ok,
        "facts": {
            "has_computed_risk": facts.get("has_computed_risk"),
            "tianyancha_ok": tyc_ok,
            "grade": (facts.get("summary") or {}).get("grade"),
            "score": (facts.get("summary") or {}).get("score"),
        },
    }
