"""可解释溯源索引（P1 可解释溯源报告）。

把一次研判的每条结论溯源到**原始出处**：
- 指标类结论 → 数据来源(ref) + 层级(tier) + PDF 页码(page，若来自文档抽取)
- 规则类结论 → 触发规则所在 YAML 文件 + 维度/严重度 +（若规则声明了）法条/监管依据

所有溯源都来自既有元数据（MetricSource.page、rules YAML 的 basis/law 字段），
**不编造任何出处**。缺字段时显式标注「未溯源」，绝不伪装成已溯源。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings

_RULE_MAP_CACHE: dict[str, str] | None = None


def _rule_file_map() -> dict[str, str]:
    """建 rule_id → 所在 YAML 文件 的映射（启动时轻量扫描，结果缓存）。"""
    global _RULE_MAP_CACHE
    if _RULE_MAP_CACHE is not None:
        return _RULE_MAP_CACHE
    m: dict[str, str] = {}
    rules_dir = Path(get_settings().bizatlas_rules_dir)
    if rules_dir.exists():
        for yf in rules_dir.glob("*.yaml"):
            try:
                docs = yaml.safe_load_all(yf.read_text(encoding="utf-8"))
                for doc in docs:
                    if isinstance(doc, dict) and doc.get("id"):
                        m[str(doc["id"])] = yf.name
            except Exception:  # noqa: BLE001
                continue
    _RULE_MAP_CACHE = m
    return m


def _regulation_of(rule_doc: dict[str, Any] | None) -> str | None:
    if not rule_doc:
        return None
    for key in ("basis", "law", "regulation", "法规", "依据"):
        v = rule_doc.get(key)
        if v:
            return str(v)
    return None


def consolidate_citations(analyze_result: dict[str, Any]) -> dict[str, Any]:
    """从 analyze 结果汇总指标溯源 + 规则溯源。

    输入 analyze_result 需含 risk.hits（规则命中）与 citations（指标观测，
    orchestrator 已产出）。缺任一项则对应列表为空，不报错。
    """
    risk = analyze_result.get("risk") or {}
    hits = list(risk.get("hits") or [])
    raw_citations = list(analyze_result.get("citations") or [])

    metric_cites = [
        {
            "id": c.get("id"),
            "label": c.get("label"),
            "page": c.get("page"),
            "tier": c.get("tier"),
            "value": c.get("value"),
            "sourced": bool(c.get("id") or c.get("label")),
        }
        for c in raw_citations
    ]

    rule_map = _rule_file_map()
    rule_cites = []
    for h in hits:
        rid = h.get("rule_id") or h.get("id")
        fname = rule_map.get(str(rid)) if rid else None
        rule_cites.append(
            {
                "rule_id": rid,
                "name": h.get("name"),
                "dimension": h.get("dimension"),
                "severity": h.get("severity"),
                "source_file": fname,
                "regulation": _regulation_of(h) if isinstance(h, dict) else None,
                "sourced": bool(fname),
            }
        )

    unsourced_rules = [r["rule_id"] for r in rule_cites if not r["sourced"]]
    return {
        "metrics": metric_cites,
        "rules": rule_cites,
        "unsourced_rules": unsourced_rules,
        "disclosure": (
            "指标结论溯源到数据来源与（若来自文档）PDF 页码；规则结论溯源到规则 YAML 文件"
            + (f"；{len(unsourced_rules)} 条规则未在 rules 目录命中源文件，已标注未溯源。"
               if unsourced_rules else "。")
        ),
    }


def render_citations_markdown(citations: dict[str, Any]) -> str:
    """把溯源索引渲染成报告「## 溯源」段落（markdown）。"""
    lines = ["## 溯源（结论可解释）", ""]
    rules = citations.get("rules") or []
    if rules:
        lines.append("**规则结论出处：**")
        for r in rules:
            src = r.get("source_file") or "未溯源"
            reg = f" · 依据：{r['regulation']}" if r.get("regulation") else ""
            lines.append(
                f"- `{r.get('rule_id')}` {r.get('name')}（{r.get('dimension')}/{r.get('severity')}）"
                f" → 规则文件：{src}{reg}"
            )
        lines.append("")
    metrics = citations.get("metrics") or []
    if metrics:
        lines.append("**指标结论出处：**")
        for m in metrics:
            page = f" · 第{m['page']}页" if m.get("page") else ""
            lines.append(f"- {m.get('label')} = {m.get('value')}（{m.get('tier')}{page}）")
        lines.append("")
    if citations.get("disclosure"):
        lines.append(f"_{citations['disclosure']}_")
        lines.append("")
    return "\n".join(lines)
