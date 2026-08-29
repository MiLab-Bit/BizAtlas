"""Number Gate 纯函数覆盖（离线，无 LLM 依赖）。"""

from __future__ import annotations

from bizatlas.llm.number_gate import (
    _close,
    collect_allowed_numbers,
    extract_numbers,
    gate_or_fallback,
    number_gate,
)


def test_extract_numbers_basic():
    # 百分比按比值归一：30% -> 0.30
    assert extract_numbers("营收 12.5 元，增长 30%") == [12.5, 0.30]
    assert extract_numbers("") == []
    assert extract_numbers(None) == []


def test_collect_allowed_numbers_variants():
    allowed = collect_allowed_numbers(
        metrics=[{"value": 0.78}, {"value": "abc"}, {"value": None}],
        risk={
            "score": 0.9,
            "dimensions": [{"score": 0.5, "weight": 0.3}],
            "quality": {"completeness": 0.8, "conflicts": 0.1},
        },
        extra=[99.0],
    )
    assert 0.78 in allowed
    assert 78.0 in allowed  # 百分比展示形式
    assert 99.0 in allowed
    assert 0.9 in allowed
    assert 0.5 in allowed
    assert 0.3 in allowed
    assert 30.0 in allowed  # weight*100
    assert 0.8 in allowed and 80.0 in allowed
    assert 0.1 in allowed
    # 常见计数整数
    assert {0.0, 1.0, 2.0, 3.0, 4.0, 5.0}.issubset(allowed)


def test_collect_allowed_numbers_objects():
    class M:
        value = 5

    allowed = collect_allowed_numbers(metrics=[M()])
    assert 5.0 in allowed


def test_close_percent_vs_ratio():
    assert _close(0.78, 78) is True
    assert _close(78, 0.78) is True
    assert _close(1.0, 1.0) is True
    assert _close(0.0, 1.0) is False


def test_number_gate_ok_and_offenders():
    allowed = {0.78, 78.0, 12.5}
    ok, off = number_gate("利润率 78%，营收 12.5 亿", allowed)
    assert ok is True and off == []
    ok2, off2 = number_gate("利润率 99%", allowed)
    assert ok2 is False and 0.99 in off2
    # 空文本视为通过
    assert number_gate("", allowed) == (True, [])
    assert number_gate(None, allowed) == (True, [])


def test_gate_or_fallback():
    allowed = {0.78}
    text, accepted = gate_or_fallback(" ratio 0.78 ", "fallback", allowed)
    assert accepted is True and text == "ratio 0.78"
    text2, accepted2 = gate_or_fallback(" ratio 0.99 ", "fallback", allowed)
    assert accepted2 is False and text2 == "fallback"
    # None / 空白 → 回退，未采纳
    t3, a3 = gate_or_fallback(None, "fb", allowed)
    assert a3 is False and t3 == "fb"
    t4, a4 = gate_or_fallback("   ", "fb", allowed)
    assert a4 is False and t4 == "fb"
