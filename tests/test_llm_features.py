from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.llm.intent import classify_intent
from bizatlas.llm.number_gate import collect_allowed_numbers, gate_or_fallback, number_gate
from bizatlas.rules.nl_compiler import compile_rule_from_nl


def test_number_gate_rejects_unknown():
    allowed = collect_allowed_numbers(
        metrics=[{"name": "资产负债率", "value": 0.78}],
        risk={"score": 55, "dimensions": [{"id": "财务", "score": 40, "weight": 0.3}]},
    )
    ok, offenders = number_gate("资产负债率约 78%，危险度 55", allowed)
    assert ok
    assert offenders == []
    bad_ok, bad = number_gate("营收增长了 1234 亿", allowed)
    assert not bad_ok
    assert bad


def test_gate_or_fallback():
    allowed = {0.25, 25.0, 1.0}
    text, accepted = gate_or_fallback("阈值 25%", "回退句", allowed)
    assert accepted
    assert "25" in text
    text2, accepted2 = gate_or_fallback("编造 999", "回退句", allowed)
    assert not accepted2
    assert text2 == "回退句"


def test_intent_heuristic_analyze():
    out = classify_intent("帮我看风险")
    assert out["intent"] == "analyze_risk"
    assert out["source"] == "heuristic"


def test_intent_heuristic_rule():
    out = classify_intent("加规则：流动比率小于 1 高风险")
    assert out["intent"] == "add_rule_nl"


def test_nl_compiler_produces_threshold():
    rule = compile_rule_from_nl("如果商誉占比超 25% 就预警")
    assert rule["condition"]["metric"] == "商誉占比"
    assert rule["status"] == "pilot"
    assert abs(rule["condition"]["value"] - 0.25) < 1e-9
    assert rule["source"] in {"nl_compiler_llm", "nl_compiler_offline"}
    assert rule["name"]
