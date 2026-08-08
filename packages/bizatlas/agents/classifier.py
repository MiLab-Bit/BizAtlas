"""分类 Agent：识别企业行业赛道，为后续规则侧重与检索提供路由。

确定性优先：基于行业字段关键词映射；仅在 LLM 可用时做细分赛道增强，
失败时退回确定性结果（绝不因 LLM 缺失而报错）。
"""

from __future__ import annotations

from typing import Any

from bizatlas.agents.base import AgentMode, AgentResult
from bizatlas.llm.polish import llm_json

# 行业大类 → 关键词（命中即归类）
_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "manufacturing": ["制造", "生产", "工厂", "工业", "机械", "设备", "材料", "化工", "能源", "建材"],
    "tech": ["科技", "软件", "互联网", "人工智能", "ai", "半导体", "芯片", "信息", "数据", "通信"],
    "retail": ["零售", "商贸", "电商", "贸易", "超市", "连锁", "消费", "门店"],
    "finance": ["金融", "银行", "保险", "证券", "基金", "资管", "信托", "租赁", "保理"],
    "services": ["服务", "咨询", "物流", "传媒", "教育", "医疗", "文旅", "建筑", "地产"],
}

# 行业大类 → 应重点核查的风险维度（对齐 risk/score.py 的五维）
_ROUTING_HINTS: dict[str, list[str]] = {
    "manufacturing": ["财务", "经营", "关联"],
    "tech": ["经营", "行业", "舆情"],
    "retail": ["经营", "舆情", "财务"],
    "finance": ["关联", "舆情", "财务"],
    "services": ["经营", "舆情", "行业"],
    "other": ["财务", "经营", "行业", "舆情", "关联"],
}


def _deterministic_category(industry: str | None) -> str:
    text = (industry or "").lower()
    for cat, kws in _INDUSTRY_KEYWORDS.items():
        if any(kw.lower() in text for kw in kws):
            return cat
    return "other"


def classify_company(
    meta: dict[str, Any],
    metrics: list[dict[str, Any]] | None = None,
) -> AgentResult:
    industry = meta.get("industry") or ""
    category = _deterministic_category(industry)
    notes: list[str] = []
    if category == "other":
        notes.append("行业字段未匹配已知类别，按通用口径研判（建议补全企业行业信息）")

    output = {
        "category": category,
        "industry_raw": industry,
        "routing_hints": list(_ROUTING_HINTS.get(category, _ROUTING_HINTS["other"])),
    }
    mode = AgentMode.DETERMINISTIC

    # 可选 LLM 增强：细分赛道与聚焦维度（失败即保留确定性结果）
    try:
        refined = llm_json(
            "根据公司名与行业判断其细分赛道与应重点核查的风险维度。"
            f"公司名：{meta.get('name') or ''}，行业：{industry}。"
            '只输出 JSON：{"category":"manufacturing|tech|retail|finance|services|other",'
            '"segment":"细分赛道","focus_dimensions":["财务","经营"]}'
        )
        if isinstance(refined, dict) and isinstance(refined.get("category"), str):
            output["category"] = refined["category"]
            output["segment"] = refined.get("segment") or ""
            if refined.get("focus_dimensions"):
                output["routing_hints"] = list(refined["focus_dimensions"])
            mode = AgentMode.LLM
    except Exception:  # noqa: BLE001
        pass

    return AgentResult(role="classifier", ok=True, mode=mode, output=output, notes=notes)
