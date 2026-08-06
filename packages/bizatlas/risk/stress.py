from __future__ import annotations

from copy import deepcopy
from typing import Any

from bizatlas.contracts.models import MetricValue, RiskResult
from bizatlas.risk.score import score_risk
from bizatlas.rules.engine import RuleEngine

SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "revenue_down_20",
        "name": "营收/盈利承压 -20%",
        "description": "毛利率、ROE 下调，经营现金流恶化",
        "shocks": {
            "毛利率": ("mul", 0.8),
            "ROE": ("mul", 0.7),
            "经营现金流/净利润": ("add", -0.2),
        },
    },
    {
        "id": "rate_up_200bp",
        "name": "利率冲击 +200bp",
        "description": "利息保障下降、杠杆压力上升",
        "shocks": {
            "利息保障倍数": ("mul", 0.6),
            "资产负债率": ("add", 0.05),
            "流动比率": ("mul", 0.9),
        },
    },
    {
        "id": "guarantee_chain",
        "name": "担保链传染",
        "description": "对外担保与质押恶化，关联风险放大",
        "shocks": {
            "对外担保比例": ("add", 0.15),
            "股权质押率": ("add", 0.1),
            "担保链层级": ("add", 1),
        },
        "events": {"重大诉讼": True},
    },
]


def _apply_shocks(metrics: list[MetricValue], shocks: dict[str, tuple[str, float]]) -> list[MetricValue]:
    out: list[MetricValue] = []
    for m in metrics:
        nm = deepcopy(m)
        if nm.name in shocks and nm.value is not None:
            op, arg = shocks[nm.name]
            if op == "mul":
                nm.value = float(nm.value) * arg
            elif op == "add":
                nm.value = float(nm.value) + arg
            elif op == "set":
                nm.value = arg
        out.append(nm)
    return out


def run_stress(
    company_id: str,
    metrics: list[MetricValue],
    events: dict[str, Any] | None = None,
    *,
    baseline: RiskResult | None = None,
) -> dict[str, Any]:
    events = dict(events or {})
    engine = RuleEngine()
    if baseline is None:
        hits = engine.match(metrics, events=events)
        baseline = score_risk(company_id, metrics, hits, events=events)

    results = []
    for sc in SCENARIOS:
        shocked = _apply_shocks(metrics, sc["shocks"])
        ev = dict(events)
        ev.update(sc.get("events") or {})
        hits = engine.match(shocked, events=ev)
        risk = score_risk(company_id, shocked, hits, events=ev)
        results.append(
            {
                "id": sc["id"],
                "name": sc["name"],
                "description": sc["description"],
                "grade": risk.grade.value,
                "score": risk.score,
                "headline": risk.headline,
                "delta_score": round(risk.score - baseline.score, 2),
                "rules_hit": len(hits),
                "top_hits": [
                    {"rule_id": h.rule_id, "severity": h.severity, "message": h.message}
                    for h in sorted(
                        hits,
                        key=lambda x: {"高": 3, "中": 2, "低": 1}.get(x.severity, 0),
                        reverse=True,
                    )[:5]
                ],
            }
        )

    worst = max(results, key=lambda r: r["score"]) if results else None
    return {
        "baseline": {
            "grade": baseline.grade.value,
            "score": baseline.score,
            "headline": baseline.headline,
        },
        "scenarios": results,
        "worst": worst,
        "note": "压力情景为确定性指标冲击后重跑规则/评分，非宏观模型预测",
    }
