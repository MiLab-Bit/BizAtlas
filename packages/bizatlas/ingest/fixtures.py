from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bizatlas.config import get_settings
from bizatlas.contracts.models import DataTier, MetricSource, MetricValue


def fixtures_root() -> Path:
    return get_settings().root / "content" / "fixtures"


def list_fixtures() -> list[str]:
    root = fixtures_root()
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "company.json").exists())


def load_fixture_company(fixture_id: str) -> dict[str, Any]:
    path = fixtures_root() / fixture_id / "company.json"
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {fixture_id}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    metrics: list[MetricValue] = []
    for item in data.get("metrics", []):
        metrics.append(
            MetricValue(
                name=item["name"],
                value=item.get("value"),
                unit=item.get("unit", ""),
                tier=DataTier(item.get("tier", "L2")),
                source=MetricSource(
                    type="cache",
                    ref=f"fixture:{fixture_id}",
                    page=item.get("page"),
                ),
                confidence=float(item.get("confidence", 0.9)),
            )
        )
    alt_metrics: list[MetricValue] = []
    for item in data.get("alt_metrics", []):
        alt_metrics.append(
            MetricValue(
                name=item["name"],
                value=item.get("value"),
                unit=item.get("unit", ""),
                tier=DataTier(item.get("tier", "L1")),
                source=MetricSource(
                    type=str(item.get("source_type") or "api"),
                    ref=str(item.get("source_ref") or "alt"),
                    page=item.get("page"),
                ),
                confidence=float(item.get("confidence", 0.75)),
            )
        )
    data["_metrics"] = metrics
    data["_alt_metrics"] = alt_metrics
    data["_events"] = data.get("events") or {}
    return data
