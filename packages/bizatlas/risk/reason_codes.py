"""FICO 式 reason codes（风险驱动因子）。

聚合各层（规则命中 / 财务困境 / 商业行为）的 Top-N 驱动因子，给出方向(+/-)与量级，
供前端"为什么是这个结果"透明展示，也对齐 FICO reason codes（驱动因子可解释性）要求。
"""
from __future__ import annotations

from typing import Any

_SEV_MAGNITUDE = {"高": 3, "中": 2, "低": 1}


def build_reason_codes(
    dimensions: list[Any],
    distress: dict[str, Any] | None = None,
    behavioral: dict[str, Any] | None = None,
    hits: list[Any] | None = None,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """生成 Top-N 风险驱动因子列表。

    Args:
        dimensions: RiskResult.dimensions（维度分）。
        distress: compute_distress 输出。
        behavioral: compute_behavioral 输出。
        hits: 规则命中列表（RuleHit）。
        top_n: 返回条数。
    """
    codes: list[dict[str, Any]] = []

    # 1) 规则命中（按严重度）
    for h in hits or []:
        if not getattr(h, "contribute_to_score", True):
            continue
        sev = getattr(h, "severity", "低") or "低"
        codes.append(
            {
                "code": getattr(h, "rule_id", "RULE"),
                "factor": getattr(h, "name", None) or getattr(h, "message", "规则命中"),
                "dimension": getattr(h, "dimension", "规则"),
                "direction": "+",
                "magnitude": _SEV_MAGNITUDE.get(sev, 1),
            }
        )

    # 2) 财务困境
    distress = distress or {}
    for key, val in (distress.get("models") or {}).items():
        if isinstance(val, dict) and val.get("zone") == "困境区":
            codes.append(
                {
                    "code": f"DISTRESS_{key.upper()}",
                    "factor": f"{key} 财务困境信号（{val.get('zone')}）",
                    "dimension": "财务",
                    "direction": "+",
                    "magnitude": 3,
                }
            )

    # 3) 商业行为
    behavioral = behavioral or {}
    for d in behavioral.get("drivers", []) or []:
        codes.append(
            {
                "code": f"BEH_{d.get('factor', 'X')}",
                "factor": f"{d.get('factor')}（{d.get('detail')}）",
                "dimension": "行为",
                "direction": "+",
                "magnitude": 2,
            }
        )

    # 量级降序，取 Top-N
    codes.sort(key=lambda c: c["magnitude"], reverse=True)
    return codes[:top_n]
