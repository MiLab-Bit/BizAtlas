from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from bizatlas.contracts.models import DataTier, MetricSource, MetricValue
from bizatlas.ingest.field_map import llm_map_metric_names, normalize_header, suggest_metric_name

KNOWN_UNITS = {
    "流动比率": "ratio",
    "速动比率": "ratio",
    "资产负债率": "ratio",
    "利息保障倍数": "ratio",
    "ROE": "ratio",
    "毛利率": "ratio",
    "经营现金流/净利润": "ratio",
    "商誉占比": "ratio",
    "客户集中度": "ratio",
}


def parse_metrics_excel(path: str | Path, *, as_of: date | None = None) -> list[MetricValue]:
    """Parse a simple metrics file: name,value[,unit] as CSV/TSV.

    Supports Chinese headers and LLM-assisted metric name alignment.
    """
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else "name,value", delimiters=",\t;")
    reader = csv.DictReader(text.splitlines(), dialect=dialect)

    # normalize headers once
    field_map: dict[str, str] = {}
    if reader.fieldnames:
        for h in reader.fieldnames:
            canon = normalize_header(h or "")
            if canon:
                field_map[h] = canon

    raw_rows: list[dict[str, str]] = []
    for row in reader:
        if field_map:
            name = ""
            raw_val = None
            unit = ""
            for h, v in row.items():
                key = field_map.get(h) or normalize_header(h or "")
                if key == "name":
                    name = (v or "").strip()
                elif key == "value":
                    raw_val = v
                elif key == "unit":
                    unit = (v or "").strip()
        else:
            name = (row.get("name") or row.get("指标") or "").strip()
            raw_val = row.get("value") or row.get("值")
            unit = (row.get("unit") or row.get("单位") or "").strip()
        if not name or raw_val is None or str(raw_val).strip() == "":
            continue
        raw_rows.append({"name": name, "value": str(raw_val).strip(), "unit": unit})

    names = [r["name"] for r in raw_rows]
    try:
        mapping = llm_map_metric_names(names)
    except Exception:  # noqa: BLE001
        mapping = {n: suggest_metric_name(n) for n in names}

    metrics: list[MetricValue] = []
    for row in raw_rows:
        name = mapping.get(row["name"], suggest_metric_name(row["name"]))
        unit = row["unit"] or KNOWN_UNITS.get(name, "")
        metrics.append(
            MetricValue(
                name=name,
                value=float(row["value"]),
                unit=unit,
                tier=DataTier.L1,
                as_of=as_of,
                source=MetricSource(type="document", ref=file_path.name, page=None),
                confidence=0.95 if name == row["name"] else 0.85,
            )
        )
    return metrics
