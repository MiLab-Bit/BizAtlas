from __future__ import annotations

import re
from typing import Any, Literal

from bizatlas.llm.polish import llm_json

IntentName = Literal[
    "analyze_risk",
    "gen_report",
    "add_rule_nl",
    "ask_doc",
    "start_dd",
    "unknown",
]


def _heuristic_intent(message: str) -> tuple[IntentName, dict[str, Any]]:
    msg = (message or "").strip()
    low = msg.lower()

    if msg.startswith("加规则") or msg.startswith("新增规则") or "加一条规则" in msg:
        text = msg
        for sep in ("：", ":", "规则", "加规则", "新增规则"):
            if sep in text and sep in ("：", ":"):
                text = text.split(sep, 1)[-1].strip()
                break
        else:
            text = re.sub(r"^(加规则|新增规则|加一条规则)\s*", "", text).strip()
        return "add_rule_nl", {"rule_text": text or msg}

    if any(k in msg for k in ("帮我看风险", "分析风险", "研判一下", "跑一下风险", "看下风险")):
        return "analyze_risk", {}

    if any(k in msg for k in ("生成报告", "出报告", "一页摘要", "信用报告", "导出报告")):
        tpl = "credit_assessment" if "信用" in msg else "risk_onepager"
        return "gen_report", {"template_id": tpl, "confirm": "导出" in msg or "word" in low or "pdf" in low}

    if any(k in msg for k in ("贷前", "尽调", "启动流程")):
        return "start_dd", {}

    if any(k in msg for k in ("多少", "是什么", "怎么样", "如何", "为何", "为什么", "？", "?")):
        return "ask_doc", {}

    return "unknown", {}


def classify_intent(message: str) -> dict[str, Any]:
    """Return {intent, slots, source: heuristic|llm}."""
    intent, slots = _heuristic_intent(message)
    if intent != "unknown":
        return {"intent": intent, "slots": slots, "source": "heuristic"}

    data = llm_json(
        "将用户话术分类为下列意图之一，并抽取槽位：\n"
        "analyze_risk | gen_report | add_rule_nl | ask_doc | start_dd | unknown\n"
        "JSON 字段：intent, rule_text?, template_id?(risk_onepager|credit_assessment), confirm?(bool)\n"
        f"用户：{message}"
    )
    if not data:
        return {"intent": "ask_doc", "slots": {}, "source": "fallback"}

    name = str(data.get("intent") or "ask_doc")
    if name not in {
        "analyze_risk",
        "gen_report",
        "add_rule_nl",
        "ask_doc",
        "start_dd",
        "unknown",
    }:
        name = "ask_doc"
    slots = {
        k: data[k]
        for k in ("rule_text", "template_id", "confirm")
        if k in data and data[k] is not None
    }
    return {"intent": name, "slots": slots, "source": "llm"}
