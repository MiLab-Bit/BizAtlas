from __future__ import annotations

import re
from typing import Any

from bizatlas.llm.client import llm_configured
from bizatlas.llm.polish import llm_json

# 仅在未配置 LLM 时作离线回退
_OP_MAP = [
    (r"(不低于|不少于|大于等于|>=|≥)", ">="),
    (r"(不高于|不超过|小于等于|<=|≤)", "<="),
    (r"(超过|大于|高于|>|＞|超)", ">"),
    (r"(低于|小于|少于|<|＜)", "<"),
]

_METRIC_ALIASES = {
    "商誉占比": "商誉占比",
    "商誉": "商誉占比",
    "流动比率": "流动比率",
    "速动比率": "速动比率",
    "资产负债率": "资产负债率",
    "杠杆": "资产负债率",
    "毛利率": "毛利率",
    "roe": "ROE",
    "净资产收益率": "ROE",
    "客户集中度": "客户集中度",
    "供应商集中度": "供应商集中度",
    "对外担保比例": "对外担保比例",
    "股权质押率": "股权质押率",
    "产能利用率": "产能利用率",
    "关联交易占比": "关联交易占比",
    "担保链层级": "担保链层级",
    "利息保障倍数": "利息保障倍数",
}

_ALLOWED_METRICS = set(_METRIC_ALIASES.values())
_ALLOWED_OPS = {">", ">=", "<", "<=", "=="}
_ALLOWED_DIMS = {"财务", "经营", "行业", "舆情", "关联"}
_ALLOWED_SEV = {"高", "中", "低"}


def _finalize_rule(
    *,
    raw: str,
    metric: str,
    op: str,
    value: float,
    severity: str,
    dimension: str,
    source: str,
    name: str | None = None,
    message: str | None = None,
    explain: str | None = None,
) -> dict[str, Any]:
    rule_id = f"P{abs(hash(raw + metric + op + str(value))) % 10_000_000:07d}"
    display = f"{value:.0%}" if 0 < abs(value) <= 1 and metric not in {
        "流动比率",
        "速动比率",
        "利息保障倍数",
        "担保链层级",
    } else str(value)
    return {
        "id": rule_id,
        "name": (name or "").strip() or f"{metric}{op}{display}",
        "dimension": dimension,
        "severity": severity,
        "status": "pilot",
        "contribute_to_score": False,
        "condition": {
            "type": "threshold",
            "metric": metric,
            "op": op,
            "value": value,
        },
        "message": (message or "").strip() or raw,
        "explain": (explain or "").strip()
        or f"当「{metric}」满足 {op} {display} 时触发（pilot，确认后计分）。",
        "source": source,
        "version": "pilot",
        "nl_text": raw,
    }


def _compile_regex(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("规则描述为空")

    metric = None
    for key, canon in _METRIC_ALIASES.items():
        if key.lower() in raw.lower() or key in raw:
            metric = canon
            break
    if not metric:
        raise ValueError("未能识别指标名，请包含如「流动比率」「商誉占比」等")

    op = None
    for pattern, symbol in _OP_MAP:
        if re.search(pattern, raw):
            op = symbol
            break
    if not op:
        raise ValueError("未能识别比较符（超过/低于/大于/小于等）")

    num = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%?", raw)
    if not num:
        raise ValueError("未能识别阈值数字")
    value = float(num.group(1))
    if "%" in raw[num.start() : num.end() + 1] or (value > 1 and metric != "利息保障倍数"):
        if metric not in {"流动比率", "速动比率", "利息保障倍数", "担保链层级"}:
            if value > 1:
                value = value / 100.0

    severity = "中"
    if any(k in raw for k in ("高风险", "严重", "红线", "高")):
        severity = "高"
    elif any(k in raw for k in ("低", "关注")):
        severity = "低"

    dimension = "财务"
    if metric in {"客户集中度", "产能利用率", "供应商集中度"}:
        dimension = "经营"
    elif metric in {"对外担保比例", "股权质押率", "关联交易占比", "担保链层级"}:
        dimension = "关联"

    return _finalize_rule(
        raw=raw,
        metric=metric,
        op=op,
        value=value,
        severity=severity,
        dimension=dimension,
        source="nl_compiler_offline",
        name=f"离线编译：{metric}",
        message=raw,
    )


def _validate_llm_rule(data: dict[str, Any], raw: str) -> dict[str, Any]:
    metric = str(data.get("metric") or "").strip()
    metric = _METRIC_ALIASES.get(metric, _METRIC_ALIASES.get(metric.lower(), metric))
    if metric not in _ALLOWED_METRICS:
        raise ValueError(f"无法映射指标「{metric}」，请改用白名单指标（如商誉占比、流动比率）")

    op = str(data.get("op") or "").strip()
    if op not in _ALLOWED_OPS:
        raise ValueError(f"比较符非法：{op}，请使用 > >= < <=")

    try:
        value = float(data.get("value"))
    except (TypeError, ValueError) as exc:
        raise ValueError("阈值不是数字") from exc

    if value > 1 and metric not in {"流动比率", "速动比率", "利息保障倍数", "担保链层级"}:
        value = value / 100.0

    severity = str(data.get("severity") or "中")
    if severity not in _ALLOWED_SEV:
        severity = "中"
    dimension = str(data.get("dimension") or "财务")
    if dimension not in _ALLOWED_DIMS:
        dimension = "财务"

    name = str(data.get("name") or "").strip()
    message = str(data.get("message") or "").strip()
    explain = str(data.get("explain") or "").strip()

    return _finalize_rule(
        raw=raw,
        metric=metric,
        op=op,
        value=value,
        severity=severity,
        dimension=dimension,
        source="nl_compiler_llm",
        name=name,
        message=message,
        explain=explain,
    )


def _compile_llm(text: str) -> dict[str, Any]:
    """LLM 编写规则 Schema；失败抛可读错误，不再静默回退正则。"""
    metrics = "、".join(sorted(_ALLOWED_METRICS))
    data = llm_json(
        "你是 BizAtlas 风控规则工程师。把用户的自然语言写成一条可执行阈值规则。\n"
        "只输出 JSON 对象，字段：\n"
        "- metric: 必须出自白名单\n"
        "- op: 仅 > >= < <=\n"
        "- value: 数字；比率类用小数（25%→0.25）；流动/速动比率、利息保障倍数、担保链层级用原值\n"
        "- severity: 高|中|低\n"
        "- dimension: 财务|经营|行业|舆情|关联\n"
        "- name: 简短规则名（中文，像制度条目，不要「自定义：」前缀）\n"
        "- message: 命中时展示的一句话告警（中文，专业简洁）\n"
        "- explain: 核对说明（中文，说明触发逻辑，可含阈值文字）\n"
        f"白名单指标：{metrics}\n"
        f"用户描述：{text}"
    )
    if not data:
        raise ValueError("LLM 未返回有效规则 JSON，请换种表述或检查 LLM 配置")
    return _validate_llm_rule(data, text.strip())


def compile_rule_from_nl(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("规则描述为空")

    # 有 LLM：只走模型编写，不再用原来的正则编译冒充
    if llm_configured():
        return _compile_llm(raw)

    return _compile_regex(raw)
