from __future__ import annotations

from collections import defaultdict
from typing import Any

from bizatlas.contracts.models import MetricValue


def detect_conflicts(
    observations: list[MetricValue],
    *,
    abs_eps: float = 0.02,
    rel_eps: float = 0.08,
) -> list[dict[str, Any]]:
    """Flag same-named metrics with material value gaps across sources."""
    by_name: dict[str, list[MetricValue]] = defaultdict(list)
    for m in observations:
        if m.value is None:
            continue
        by_name[m.name].append(m)

    conflicts: list[dict[str, Any]] = []
    for name, items in by_name.items():
        if len(items) < 2:
            continue
        # distinct sources only
        keyed: dict[str, MetricValue] = {}
        for m in items:
            src = m.source.ref if m.source else "unknown"
            keyed[f"{src}|{m.tier.value}"] = m
        if len(keyed) < 2:
            continue
        vals = [m.value for m in keyed.values() if m.value is not None]
        lo, hi = min(vals), max(vals)
        span = hi - lo
        base = max(abs(hi), abs(lo), 1e-9)
        if span < abs_eps and span / base < rel_eps:
            continue
        conflicts.append(
            {
                "metric": name,
                "delta": round(span, 4),
                "rel_delta": round(span / base, 4),
                "values": [
                    {
                        "value": m.value,
                        "tier": m.tier.value,
                        "source": m.source.ref if m.source else None,
                        "source_type": m.source.type if m.source else None,
                        "page": m.source.page if m.source else None,
                        "confidence": m.confidence,
                    }
                    for m in keyed.values()
                ],
                "note": "多源数值不一致，未自动裁定；研判默认采用主源（上传/fixture 主表）",
            }
        )
    return conflicts
