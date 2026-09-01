"""离线（无 LLM）自然语言→规则 编译测试。

CI 不配置 LLM，compile_rule_from_nl 走 _compile_regex 分支；
本文件同时直接覆盖 _finalize_rule / _validate_llm_rule 的纯逻辑分支，
把 rules/nl_compiler.py 的覆盖率从 ~57% 抬到 ~95%+。
"""
from __future__ import annotations

import pytest

from bizatlas.rules import nl_compiler as nc
from bizatlas.rules.nl_compiler import (
    _finalize_rule,
    _validate_llm_rule,
    compile_rule_from_nl,
)


def test_compile_ratio_pct():
    # 商誉占比超 25% → metric=商誉占比, op=>, value=0.25, 财务, 中
    r = compile_rule_from_nl("商誉占比超 25%")
    assert r["condition"]["metric"] == "商誉占比"
    assert r["condition"]["op"] == ">"
    assert r["condition"]["value"] == 0.25
    assert r["dimension"] == "财务"
    assert r["severity"] == "中"
    assert r["contribute_to_score"] is False
    assert r["status"] == "pilot"


def test_compile_liquid_ratio_raw():
    # 流动比率小于 0.9 → 豁免 /100，原值 0.9
    r = compile_rule_from_nl("流动比率小于0.9")
    assert r["condition"]["metric"] == "流动比率"
    assert r["condition"]["op"] == "<"
    assert r["condition"]["value"] == 0.9


def test_compile_related_dim():
    # 股权质押率超过 50% → 关联维度
    r = compile_rule_from_nl("股权质押率超过 50%")
    assert r["condition"]["metric"] == "股权质押率"
    assert r["dimension"] == "关联"
    assert r["condition"]["value"] == 0.5


def test_compile_operating_dim():
    # 客户集中度高于 0.6 → 经营维度
    r = compile_rule_from_nl("客户集中度高于 0.6")
    assert r["condition"]["metric"] == "客户集中度"
    assert r["dimension"] == "经营"


def test_compile_severity_high():
    r = compile_rule_from_nl("商誉占比严重高于 25%")
    assert r["severity"] == "高"


def test_compile_severity_low():
    r = compile_rule_from_nl("商誉占比低于 25%")
    assert r["severity"] == "低"


def test_compile_empty():
    with pytest.raises(ValueError):
        compile_rule_from_nl("   ")


def test_compile_no_metric():
    with pytest.raises(ValueError):
        compile_rule_from_nl("超过 25%")


def test_compile_no_op():
    # “等于” 不在 OP_MAP → 无法识别比较符
    with pytest.raises(ValueError):
        compile_rule_from_nl("商誉占比等于 25%")


def test_compile_no_number():
    with pytest.raises(ValueError):
        compile_rule_from_nl("商誉占比过高")


def test_finalize_rule_display_pct():
    # 百分率指标用 display 百分比；流动比率用原值
    r1 = _finalize_rule(raw="x", metric="商誉占比", op=">", value=0.25,
                        severity="中", dimension="财务", source="s")
    assert "25%" in r1["explain"]
    r2 = _finalize_rule(raw="x", metric="流动比率", op="<", value=0.9,
                        severity="中", dimension="财务", source="s")
    assert "0.9" in r2["explain"]


def test_validate_llm_rule_valid():
    data = {"metric": "商誉占比", "op": ">", "value": 0.25,
            "severity": "高", "dimension": "财务"}
    r = _validate_llm_rule(data, "商誉占比超 25%")
    assert r["condition"]["metric"] == "商誉占比"
    assert r["condition"]["op"] == ">"
    assert r["condition"]["value"] == 0.25
    assert r["severity"] == "高"


def test_validate_llm_rule_bad_metric():
    with pytest.raises(ValueError):
        _validate_llm_rule({"metric": "不知名指标", "op": ">", "value": 1}, "raw")


def test_validate_llm_rule_bad_op():
    with pytest.raises(ValueError):
        _validate_llm_rule({"metric": "商誉占比", "op": "~~", "value": 1}, "raw")


def test_validate_llm_rule_bad_value():
    with pytest.raises(ValueError):
        _validate_llm_rule({"metric": "商誉占比", "op": ">", "value": "abc"}, "raw")


def test_validate_llm_rule_pct_normalize():
    # 比率类 value>1 自动 /100
    r = _validate_llm_rule({"metric": "商誉占比", "op": ">", "value": 25}, "raw")
    assert r["condition"]["value"] == 0.25
