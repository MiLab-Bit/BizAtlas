from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.contracts.models import MetricValue


def benchmarks_path() -> Path:
    return get_settings().root / "content" / "industry" / "benchmarks.yaml"


def load_benchmarks() -> dict[str, Any]:
    path = benchmarks_path()
    if not path.exists():
        return {"industries": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data


def compare_to_industry(
    industry: str | None,
    metrics: list[MetricValue],
) -> dict[str, Any]:
    data = load_benchmarks()
    industries = data.get("industries") or {}
    key = industry if industry in industries else None
    if key is None:
        # fuzzy contains
        for name in industries:
            if industry and (industry in name or name in industry):
                key = name
                break
    if key is None:
        key = "默认" if "默认" in industries else (next(iter(industries), None))

    table = (industries.get(key) or {}).get("metrics") or {}
    metric_map = {m.name: m for m in metrics if m.value is not None}
    rows: list[dict[str, Any]] = []
    flags = 0
    for name, bench in table.items():
        mv = metric_map.get(name)
        if mv is None:
            continue
        median = bench.get("median")
        status = "ok"
        note = "接近行业中位"
        if bench.get("warn_above") is not None and mv.value is not None and mv.value > float(bench["warn_above"]):
            status = "warn_high"
            note = f"高于警戒 {bench['warn_above']}"
            flags += 1
        elif bench.get("warn_below") is not None and mv.value is not None and mv.value < float(bench["warn_below"]):
            status = "warn_low"
            note = f"低于警戒 {bench['warn_below']}"
            flags += 1
        elif median is not None and mv.value is not None:
            gap = mv.value - float(median)
            note = f"相对中位 {gap:+.2%}" if abs(float(median)) < 2 else f"相对中位 {gap:+.2f}"
        rows.append(
            {
                "metric": name,
                "company": mv.value,
                "industry_median": median,
                "warn_above": bench.get("warn_above"),
                "warn_below": bench.get("warn_below"),
                "status": status,
                "note": note,
                "tier": "L3",
            }
        )

    return {
        "industry": key,
        "label": (industries.get(key) or {}).get("label") or key,
        "rows": rows,
        "warn_count": flags,
        "source": "content/industry/benchmarks.yaml",
        "note": "静态行业参数（L3）；仅作对标提示，不替代主源财务",
    }
