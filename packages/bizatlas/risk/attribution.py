from __future__ import annotations

from typing import Any

from bizatlas.contracts.models import DimensionScore, MetricValue, RuleHit
from bizatlas.risk.score import DIMENSION_WEIGHTS, SEVERITY_SCORE


def build_attribution(
    dimensions: list[DimensionScore],
    hits: list[RuleHit],
    metrics: list[MetricValue] | None = None,
) -> list[dict[str, Any]]:
    """Per-dimension drill-down: contributing hits + metric drivers."""
    metrics = metrics or []
    metric_map = {m.name: m for m in metrics}
    total_weighted = sum(d.score * d.weight for d in dimensions) or 1.0

    out: list[dict[str, Any]] = []
    for dim in dimensions:
        dim_hits = [h for h in hits if (h.dimension or "财务") == dim.id]
        # also bucket unknown dims into 财务 already handled in score
        drivers: list[dict[str, Any]] = []
        seen: set[str] = set()
        for h in dim_hits:
            for mv in h.metrics:
                if mv.name in seen:
                    continue
                seen.add(mv.name)
                drivers.append(
                    {
                        "name": mv.name,
                        "value": mv.value,
                        "tier": mv.tier.value,
                        "source": mv.source.ref if mv.source else None,
                        "page": mv.source.page if mv.source else None,
                    }
                )
            # fallback: parse metric name from condition explain
            if not h.metrics and "=" in (h.explain or ""):
                name = (h.explain or "").split("=", 1)[0].strip()
                if name and name not in seen and name in metric_map:
                    mv = metric_map[name]
                    seen.add(name)
                    drivers.append(
                        {
                            "name": mv.name,
                            "value": mv.value,
                            "tier": mv.tier.value,
                            "source": mv.source.ref if mv.source else None,
                            "page": mv.source.page if mv.source else None,
                        }
                    )

        severity_mass = sum(SEVERITY_SCORE.get(h.severity, 10.0) for h in dim_hits if h.contribute_to_score)
        # 去重：同 rule_id + message + explain 只保留一条（避免反复 NL 入库刷屏）
        uniq_hits: list[RuleHit] = []
        seen_hit: set[str] = set()
        for h in sorted(dim_hits, key=lambda x: SEVERITY_SCORE.get(x.severity, 0), reverse=True):
            key = f"{h.rule_id}|{h.message}|{h.explain}"
            if key in seen_hit:
                continue
            seen_hit.add(key)
            uniq_hits.append(h)

        out.append(
            {
                "id": dim.id,
                "score": dim.score,
                "weight": dim.weight,
                "weighted_contribution": round(dim.score * dim.weight, 2),
                "share_of_total": round((dim.score * dim.weight) / total_weighted, 3),
                "hit_count": len(uniq_hits),
                "severity_mass": round(severity_mass, 2),
                "hits": [
                    {
                        "rule_id": h.rule_id,
                        "name": h.name,
                        "severity": h.severity,
                        "message": h.message,
                        "explain": h.explain,
                        "contribute_to_score": h.contribute_to_score,
                    }
                    for h in uniq_hits
                ],
                "drivers": drivers,
            }
        )

    # ensure all five dims present even if score returned subset
    present = {d["id"] for d in out}
    for dim_id, weight in DIMENSION_WEIGHTS.items():
        if dim_id not in present:
            out.append(
                {
                    "id": dim_id,
                    "score": 0.0,
                    "weight": weight,
                    "weighted_contribution": 0.0,
                    "share_of_total": 0.0,
                    "hit_count": 0,
                    "severity_mass": 0.0,
                    "hits": [],
                    "drivers": [],
                }
            )
    order = list(DIMENSION_WEIGHTS.keys())
    out.sort(key=lambda d: order.index(d["id"]) if d["id"] in order else 99)
    return out
