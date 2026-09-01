from __future__ import annotations

from typing import Any

from bizatlas.llm.polish import llm_json
from bizatlas.rules.nl_compiler import _ALLOWED_METRICS, _METRIC_ALIASES

# CSV 常见表头别名 → 规范列
COLUMN_ALIASES = {
    "name": "name",
    "指标": "name",
    "指标名": "name",
    "metric": "name",
    "字段": "name",
    "value": "value",
    "值": "value",
    "数值": "value",
    "amount": "value",
    "unit": "unit",
    "单位": "unit",
}


def normalize_header(header: str) -> str | None:
    key = (header or "").strip()
    if not key:
        return None
    return COLUMN_ALIASES.get(key) or COLUMN_ALIASES.get(key.lower())


def suggest_metric_name(raw_name: str) -> str:
    """Map free-form metric label to canonical name; identity if unknown."""
    name = (raw_name or "").strip()
    if not name:
        return name
    if name in _ALLOWED_METRICS:
        return name
    alias = _METRIC_ALIASES.get(name) or _METRIC_ALIASES.get(name.lower())
    if alias:
        return alias
    return name


def llm_map_metric_names(names: list[str]) -> dict[str, str]:
    """Ask LLM to map odd labels → whitelist; invalid mappings ignored."""
    unknown = [n for n in names if suggest_metric_name(n) not in _ALLOWED_METRICS and n not in _ALLOWED_METRICS]
    if not unknown:
        return {n: suggest_metric_name(n) for n in names}

    allowed = "、".join(sorted(_ALLOWED_METRICS))
    data = llm_json(
        "将下列指标名映射到白名单标准名。只输出 JSON 对象：原始名 → 标准名。\n"
        f"白名单：{allowed}\n"
        "无法映射的键不要输出。\n"
        f"待映射：{unknown}"
    )
    mapping: dict[str, str] = {n: suggest_metric_name(n) for n in names}
    if not data:
        return mapping
    for raw, canon in data.items():
        c = str(canon).strip()
        if c in _ALLOWED_METRICS:
            mapping[str(raw)] = c
    return mapping


def remap_metric_dicts(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    names = [str(r.get("name") or "") for r in rows if r.get("name")]
    mapping = llm_map_metric_names(names)
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        raw = str(item.get("name") or "")
        item["name"] = mapping.get(raw, suggest_metric_name(raw))
        if item["name"] != raw:
            item["name_mapped_from"] = raw
        out.append(item)
    return out, mapping
