from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.contracts.models import MetricValue, RuleHit


def load_rules(rules_dir: str | Path | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    directory = Path(rules_dir or settings.bizatlas_rules_dir)
    rules: list[dict[str, Any]] = []
    if not directory.exists():
        return rules
    for path in sorted(directory.glob("*.yaml")):
        if path.name.lower() == "readme.md":
            continue
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            rules.extend(data)
        elif isinstance(data, dict) and "rules" in data:
            rules.extend(data["rules"])
    return rules


def _get_metric(metrics: dict[str, MetricValue], name: str) -> MetricValue | None:
    if name in metrics:
        return metrics[name]
    for key, value in metrics.items():
        if key == name or value.name == name:
            return value
    return None


def _eval_threshold(cond: dict[str, Any], metrics: dict[str, MetricValue]) -> tuple[bool, str]:
    metric_name = str(cond.get("metric", ""))
    op = str(cond.get("op", ""))
    expected = cond.get("value")
    mv = _get_metric(metrics, metric_name)
    if mv is None or mv.value is None:
        return False, f"{metric_name} 缺失，跳过"
    actual = mv.value
    ok = False
    if op == "<":
        ok = actual < float(expected)
    elif op == "<=":
        ok = actual <= float(expected)
    elif op == ">":
        ok = actual > float(expected)
    elif op == ">=":
        ok = actual >= float(expected)
    elif op == "==":
        ok = actual == float(expected)
    explain = f"{metric_name}={actual} {op} {expected} → {'命中' if ok else '未命中'}"
    return ok, explain


def _eval_event(cond: dict[str, Any], events: dict[str, Any]) -> tuple[bool, str]:
    flag = str(cond.get("event", ""))
    hit = bool(events.get(flag, False))
    return hit, f"事件 {flag}={'是' if hit else '否'}"


class RuleEngine:
    def __init__(self, rules: list[dict[str, Any]] | None = None) -> None:
        if rules is not None:
            self.rules = rules
        else:
            try:
                from bizatlas.rules.store import load_all_rules

                self.rules = load_all_rules()
            except Exception:  # noqa: BLE001
                self.rules = load_rules()

    def match(
        self,
        metrics: list[MetricValue] | dict[str, MetricValue],
        events: dict[str, Any] | None = None,
    ) -> list[RuleHit]:
        events = events or {}
        if isinstance(metrics, list):
            metric_map = {m.name: m for m in metrics}
        else:
            metric_map = metrics

        hits: list[RuleHit] = []
        for rule in self.rules:
            status = str(rule.get("status", "active"))
            if status == "disabled":
                continue
            cond = rule.get("condition") or {}
            ctype = str(cond.get("type", "threshold"))
            matched = False
            explain = ""
            used: list[MetricValue] = []

            if ctype == "threshold":
                matched, explain = _eval_threshold(cond, metric_map)
                mv = _get_metric(metric_map, str(cond.get("metric", "")))
                if mv:
                    used.append(mv)
            elif ctype == "event":
                matched, explain = _eval_event(cond, events)
            elif ctype == "composite":
                parts = cond.get("all") or []
                results = []
                for part in parts:
                    if part.get("type") == "event":
                        ok, ex = _eval_event(part, events)
                    else:
                        ok, ex = _eval_threshold(part, metric_map)
                        mv = _get_metric(metric_map, str(part.get("metric", "")))
                        if mv:
                            used.append(mv)
                    results.append((ok, ex))
                matched = all(r[0] for r in results) if results else False
                explain = " AND ".join(r[1] for r in results)
            else:
                continue

            if not matched:
                continue

            contribute = status != "pilot" and bool(rule.get("contribute_to_score", True))
            hits.append(
                RuleHit(
                    rule_id=str(rule.get("id")),
                    name=str(rule.get("name", rule.get("id"))),
                    dimension=str(rule.get("dimension", "")),
                    severity=str(rule.get("severity", "中")),
                    message=str(rule.get("message") or rule.get("name") or "规则命中"),
                    metrics=used,
                    contribute_to_score=contribute,
                    explain=explain,
                )
            )
        return hits
