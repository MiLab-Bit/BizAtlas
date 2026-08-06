from __future__ import annotations

from typing import Any

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.llm.intent import classify_intent
from bizatlas.orchestrator.analyze import generate_credit_report, generate_onepager_report, run_analyze
from bizatlas.rag.simple import ask_company
from bizatlas.rules.nl_compiler import compile_rule_from_nl
from bizatlas.rules.store import save_pilot_rule
from bizatlas.workflow.due_diligence import start_due_diligence


def handle_agent_message(
    message: str,
    *,
    company_id: str | None = None,
    fixture_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Intent router for Copilot: analyze / report / rule / ask / dd."""
    ctx = context or {}
    classified = classify_intent(message)
    intent = classified["intent"]
    slots = classified.get("slots") or {}
    target = company_id or fixture_id or ctx.get("company_id") or ctx.get("fixture_id")

    if intent == "add_rule_nl":
        text = str(slots.get("rule_text") or message)
        for prefix in ("加规则", "新增规则", "加一条规则"):
            if text.startswith(prefix):
                text = text[len(prefix) :].lstrip(" ：:")
        rule = compile_rule_from_nl(text)
        saved = save_pilot_rule(rule)
        return {
            "type": "rule",
            "intent": intent,
            "intent_source": classified.get("source"),
            "answer": f"已入库 pilot 规则 `{saved.get('id')}`：{saved.get('name')}（确认后才计分）",
            "rule": saved,
        }

    if intent == "analyze_risk":
        if not target:
            return {
                "type": "clarify",
                "intent": intent,
                "answer": "请先选择演示案例或上传企业，再让我研判风险。",
            }
        result = run_analyze(
            AnalyzeRequest(
                company_id=str(target),
                intent="analyze_risk",
                options={"include_stress": True, "include_kg": True},
            )
        )
        summary = result.get("summary") or {}
        return {
            "type": "analyze",
            "intent": intent,
            "intent_source": classified.get("source"),
            "answer": (
                f"研判完成：{summary.get('grade')} / {summary.get('score')}。"
                f"{summary.get('headline') or ''}"
            ),
            "summary": summary,
            "company": result.get("company"),
            "analyze": {
                "grade": summary.get("grade"),
                "score": summary.get("score"),
                "headline": summary.get("headline"),
                "rules_hit": result.get("rules_hit"),
                "conflicts": (result.get("risk") or {}).get("quality", {}).get("conflicts"),
            },
        }

    if intent == "gen_report":
        if not target:
            return {
                "type": "clarify",
                "intent": intent,
                "answer": "请先选择企业/案例，再生成报告。",
            }
        tpl = str(slots.get("template_id") or "risk_onepager")
        confirm = bool(slots.get("confirm"))
        if tpl == "credit_assessment":
            out = generate_credit_report(str(target), confirm_export=confirm)
        else:
            out = generate_onepager_report(str(target), confirm_export=confirm)
        return {
            "type": "report",
            "intent": intent,
            "intent_source": classified.get("source"),
            "answer": (
                f"已生成「{out.get('analysis_title') or tpl}」"
                f"（{out.get('status_label') or out.get('status')}）。"
                + (" 含 Word/PDF 导出。" if confirm else " 可继续要求导出。")
            ),
            "report": {
                "report_id": out.get("report_id"),
                "analysis_title": out.get("analysis_title"),
                "status": out.get("status"),
                "markdown": out.get("markdown"),
            },
        }

    if intent == "start_dd":
        data = start_due_diligence(
            company_id=company_id,
            fixture_id=fixture_id or (target if target in {"healthy", "risky", "defaulted"} else None),
        )
        return {
            "type": "workflow",
            "intent": intent,
            "intent_source": classified.get("source"),
            "answer": f"已启动贷前尽调，当前阶段：{data.get('stage')}",
            "workflow": {"id": data.get("id"), "stage": data.get("stage")},
        }

    # ask_doc / unknown → RAG（可带研判上下文提示）
    rag = ask_company(
        message,
        company_id=company_id,
        fixture_id=fixture_id
        or (company_id if company_id in {"healthy", "risky", "defaulted"} else None),
    )
    prefix = ""
    if ctx.get("grade"):
        prefix = (
            f"（当前上下文：等级 {ctx.get('grade')} · 得分 {ctx.get('score')} · "
            f"命中 {ctx.get('rules_hit', '—')} · 冲突 {ctx.get('conflicts', '—')}）\n"
        )
    return {
        "type": "rag",
        "intent": "ask_doc",
        "intent_source": classified.get("source"),
        "answer": prefix + (rag.get("answer") or ""),
        "citations": rag.get("citations") or [],
        "confidence": rag.get("confidence"),
        "llm_used": rag.get("llm_used"),
    }
