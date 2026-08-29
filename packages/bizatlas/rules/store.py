from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.data.db import get_connection
from bizatlas.rules.engine import load_rules as load_file_rules


def custom_rules_path() -> Path:
    return Path(get_settings().bizatlas_rules_dir) / "custom_pilot.yaml"


def load_all_rules() -> list[dict[str, Any]]:
    rules = load_file_rules()
    # DB custom rules
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, dimension, payload_json, version, status FROM rules"
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        payload = json.loads(r["payload_json"] or "{}")
        payload.setdefault("id", r["id"])
        payload.setdefault("name", r["name"])
        payload.setdefault("dimension", r["dimension"])
        payload.setdefault("status", r["status"] or "pilot")
        payload.setdefault("version", r["version"] or "pilot")
        # avoid dup ids
        if not any(x.get("id") == payload.get("id") for x in rules):
            rules.append(payload)
    return rules


def save_pilot_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rule = dict(rule)
    rule["status"] = rule.get("status") or "pilot"
    rule["contribute_to_score"] = bool(rule.get("contribute_to_score", False))

    # append yaml
    path = custom_rules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        existing = list(data.get("rules") or [])
    existing = [r for r in existing if r.get("id") != rule.get("id")]
    existing.append(rule)
    path.write_text(
        yaml.safe_dump({"rules": existing}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # upsert db
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO rules (id, name, dimension, payload_json, version, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                rule["id"],
                rule.get("name"),
                rule.get("dimension"),
                json.dumps(rule, ensure_ascii=False),
                rule.get("version", "pilot"),
                rule.get("status", "pilot"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return rule


def activate_rule(rule_id: str) -> dict[str, Any]:
    rules = load_all_rules()
    target = next((r for r in rules if r.get("id") == rule_id), None)
    if not target:
        raise ValueError(f"rule not found: {rule_id}")
    target["status"] = "active"
    target["contribute_to_score"] = True
    return save_pilot_rule(target)
