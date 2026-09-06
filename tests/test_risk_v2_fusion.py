"""B-RCF v2.0.1 融合层单测：量纲统一 / 审慎叠加 / 数据缺口不参与。

背景（2026-09-06 修复）:
融合层原实现把困境层的「违约概率 PD」直接 PD×100 当作 0-100 严重度分与规则分
加权平均；同时 compute_distress 在 Ohlson/Altman 均无法计算时（fixture 只有比率
指标、缺原始报表科目）仍因 Beneish 占位判定 available=True，使 pd=None 被当成
「风险 0」参与加权，直接把 risky 的规则分 96.2 稀释到 48.1（BLACK → ORANGE），
即典型的把未知当安全。

本文件锁住三条不变量：
1. 数据缺口（PD 缺失 / 行为层已知维度不足）绝不参与融合，更不得拉低规则分；
2. PD 与严重度分在对数几率尺度换算，量纲可比且单调；
3. 融合只升不降：其他层仅在显著劣于规则分时向上叠加。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import MetricValue, RiskGrade, RiskResult, RuleHit
from bizatlas.risk.behavioral import compute_behavioral
from bizatlas.risk.distress import compute_distress
from bizatlas.risk.reason_codes import build_reason_codes
from bizatlas.risk.score import (
    BEHAVIORAL_MIN_COMPLETENESS,
    UPLIFT_MIN_DELTA,
    blend_severity,
    enrich_risk,
    severity_from_pd,
)


def _full_statements() -> list[MetricValue]:
    """完整原始报表科目（可让 Altman Z'' 与 Ohlson O-Score 同时算出）。"""
    return [
        MetricValue(name="总资产", value=1000.0),
        MetricValue(name="负债合计", value=800.0),
        MetricValue(name="营运资金", value=50.0),
        MetricValue(name="留存收益", value=100.0),
        MetricValue(name="利润总额", value=60.0),
        MetricValue(name="所有者权益合计", value=200.0),
        MetricValue(name="流动资产", value=400.0),
        MetricValue(name="流动负债", value=350.0),
        MetricValue(name="净利润", value=40.0),
    ]


def _ratios_only() -> list[MetricValue]:
    """只有比率指标（无原始报表科目）——fixture/demo 数据的典型形态。"""
    return [
        MetricValue(name="资产负债率", value=0.8),
        MetricValue(name="流动比率", value=1.14),
    ]


def _risk(score: float = 30.0, grade: RiskGrade = RiskGrade.YELLOW) -> RiskResult:
    return RiskResult(company_id="co-test", grade=grade, score=score, headline="测试主体")


# --------------------------------------------------------------------------- 1
def test_severity_from_pd_handles_gaps_and_bounds():
    assert severity_from_pd(None) is None
    assert severity_from_pd(0.001) == 0.0
    assert severity_from_pd(0.99) == 100.0
    # 越界输入被 clamp，不产生 >100 或 <0 的严重度
    assert severity_from_pd(0.0) == 0.0
    assert severity_from_pd(1.0) == 100.0


def test_severity_from_pd_monotonic_and_anchored():
    vals = [severity_from_pd(p) for p in (0.001, 0.01, 0.05, 0.13, 0.5, 0.95)]
    assert vals == sorted(vals), "PD 升高时严重度必须单调不减"
    assert all(0.0 <= v <= 100.0 for v in vals)
    # 对数几率锚点（与评分卡 PDO 口径一致）
    assert 19.0 <= severity_from_pd(0.01) <= 22.0
    assert 33.0 <= severity_from_pd(0.05) <= 36.0
    assert 42.0 <= severity_from_pd(0.13) <= 45.0
    assert 59.0 <= severity_from_pd(0.50) <= 61.0
    assert 84.0 <= severity_from_pd(0.95) <= 87.0


# --------------------------------------------------------------------------- 2
def test_blend_severity_never_lowers_rule_score():
    """只升不降：数据缺口或更低的层都不得拉低规则分（risky 96.2 稀释回归）。"""
    combined, audit = blend_severity(96.2, {"distress": None, "behavioral": None})
    assert combined == 96.2
    assert audit["uplift_total"] == 0.0
    assert audit["uplift_by_layer"] == {}

    combined, _ = blend_severity(80.0, {"distress": 10.0})
    assert combined == 80.0, "层严重度低于规则分时不得下调"


def test_blend_severity_uplift_and_threshold():
    # 显著劣化（差值 ≥ UPLIFT_MIN_DELTA）按权重上调
    combined, audit = blend_severity(20.0, {"distress": 90.0})
    assert combined == round(20.0 + 0.3 * 70.0, 2)
    assert audit["uplift_by_layer"]["distress"] == round(0.3 * 70.0, 2)

    # 差值不足阈值 → 视为噪声，不上调
    combined, audit = blend_severity(20.0, {"distress": 20.0 + UPLIFT_MIN_DELTA - 1})
    assert combined == 20.0
    assert audit["uplift_total"] == 0.0

    # 多层同时上调并 clamp 在 100
    combined, _ = blend_severity(20.0, {"distress": 100.0, "behavioral": 100.0})
    assert combined == 60.0
    assert combined <= 100.0


# --------------------------------------------------------------------------- 3
def test_compute_distress_with_full_statements():
    d = compute_distress(_full_statements())
    assert d["available"] is True
    assert d["pd"] is not None and 0.0 < d["pd"] < 1.0
    assert "altman" in d["models"] and "ohlson" in d["models"]
    # 优先取 Ohlson PD
    assert d["pd"] == d["models"]["ohlson"]["pd"]
    assert d["missing"] == []


def test_compute_distress_data_gap_is_not_available():
    """核心回归：缺原始科目时不得伪装成「风险 0」可用。"""
    d = compute_distress(_ratios_only())
    assert d["pd"] is None
    assert d["available"] is False, "Beneish 不可用占位不得让 available 为真"
    assert "beneish" not in d["models"], "不可用模型不应计入 models"
    assert any("Beneish M-Score 不可用" in n for n in d["notes"])
    assert "ta" in d["missing"]


def test_compute_distress_falls_back_to_stored_altman():
    metrics = _ratios_only() + [MetricValue(name="Z值(Altman)", value=0.8)]
    d = compute_distress(metrics)
    assert d["available"] is True
    assert d["models"]["altman"]["zone"] == "困境区"
    assert d["pd"] == 0.65, "无 Ohlson 时回退 Altman 区带先验（困境区 0.65）"


def test_compute_distress_empty_metrics():
    d = compute_distress([])
    assert d["available"] is False
    assert d["pd"] is None


# --------------------------------------------------------------------------- 4
def test_compute_behavioral_hits_and_gaps():
    b = compute_behavioral({"失信被执行": True, "行政处罚": 2})
    assert b["available"] is True
    assert b["scores"]["被执行失信"] == 45.0
    assert b["scores"]["行政处罚"] == 60.0
    assert b["scores"]["司法涉诉"] is None, "无信号维度必须标 N/A 而不是 0"
    # (45*0.30 + 60*0.20) / (0.30+0.20) = 51.0
    assert b["composite"] == 51.0
    assert b["completeness"] == 0.4
    assert set(b["data_gap"]) == {"司法涉诉", "经营异常", "股权风险"}


def test_compute_behavioral_empty_events():
    b = compute_behavioral({})
    assert b["available"] is False
    assert b["composite"] == 0.0
    assert b["completeness"] == 0.0
    assert len(b["data_gap"]) == 5


# --------------------------------------------------------------------------- 5
def test_enrich_risk_gap_layers_do_not_dilute():
    """端到端回归：困境层缺口 + 行为层覆盖不足时，规则分原样保留。"""
    risk = _risk(score=96.2, grade=RiskGrade.BLACK)
    out = enrich_risk(
        risk,
        _ratios_only(),
        {},
        distress={"available": False, "pd": None, "models": {}, "missing": ["ta"], "notes": []},
        behavioral={"available": True, "composite": 30.0, "completeness": 0.2, "drivers": []},
    )
    assert out.score == 96.2
    assert out.modules["layer_severity"] == {"rule": 96.2, "distress": None, "behavioral": None}
    assert out.modules["uplift_total"] == 0.0
    assert out.modules["blend_weights"]["distress"] == 0.0
    assert out.modules["version"] == "2.0.1"


def test_enrich_risk_uplifts_on_severe_distress():
    """财务困境显著劣于规则分 → 向上叠加（只升不降）。"""
    risk = _risk(score=20.0)
    out = enrich_risk(
        risk,
        _full_statements(),
        {},
        distress={"available": True, "pd": 0.95, "models": {}, "missing": [], "notes": []},
        behavioral={"available": False, "composite": 0.0, "completeness": 0.0, "drivers": []},
    )
    assert out.score > 20.0
    assert out.modules["layer_severity"]["distress"] == severity_from_pd(0.95)
    assert out.modules["uplift_by_layer"]["distress"] > 0


def test_enrich_risk_behavioral_partial_coverage_excluded():
    """行为层已知维度不足 BEHAVIORAL_MIN_COMPLETENESS 时不参与融合。"""
    risk = _risk(score=40.0)
    events = {"行政处罚": 1}
    out = enrich_risk(risk, [], events)
    beh = out.modules["behavioral"]
    assert beh["completeness"] < BEHAVIORAL_MIN_COMPLETENESS
    assert out.modules["layer_severity"]["behavioral"] is None
    assert out.score == 40.0


def test_enrich_risk_veto_keeps_black():
    risk = _risk(score=76.1, grade=RiskGrade.BLACK)
    risk.veto.triggered = True
    risk.veto.reason = "命中失信被执行人"
    out = enrich_risk(risk, _ratios_only(), {})
    assert out.grade == RiskGrade.BLACK


# --------------------------------------------------------------------------- 6
def test_build_reason_codes_aggregates_layers():
    hits = [
        RuleHit(rule_id="R1001", name="短期偿债能力红线", dimension="财务",
                severity="高", message="流动比率过低"),
        RuleHit(rule_id="R9999", name="仅提示规则", dimension="财务",
                severity="低", message="pilot 规则", contribute_to_score=False),
    ]
    codes = build_reason_codes(
        [],
        distress={"models": {"altman": {"zone": "困境区"}}},
        behavioral={"drivers": [{"factor": "行政处罚", "detail": "2 条信号命中"}]},
        hits=hits,
    )
    by_code = {c["code"]: c for c in codes}
    assert "R1001" in by_code and by_code["R1001"]["magnitude"] == 3
    assert "R9999" not in by_code, "不计分规则不应进入 reason codes"
    assert by_code["DISTRESS_ALTMAN"]["dimension"] == "财务"
    assert by_code["BEH_行政处罚"]["dimension"] == "行为"
    # 量级降序
    assert [c["magnitude"] for c in codes] == sorted(
        (c["magnitude"] for c in codes), reverse=True
    )


def test_build_reason_codes_top_n():
    hits = [
        RuleHit(rule_id=f"R{i}", name=f"规则{i}", dimension="财务", severity="高", message="m")
        for i in range(12)
    ]
    assert len(build_reason_codes([], hits=hits, top_n=5)) == 5


# ------------------------------------------------- 边界：Beneish / 除零 / 事件值类型
def test_compute_distress_beneish_with_full_variables():
    """补齐 8 个 Beneish 变量后应给出 M-Score 与操纵嫌疑判定。"""
    metrics = _full_statements() + [
        MetricValue(name=k, value=v)
        for k, v in {
            "DSRI": 1.1,
            "GMI": 1.0,
            "AQI": 0.9,
            "SGI": 1.05,
            "DEPI": 1.0,
            "SGAI": 0.95,
            "TATA": 0.02,
            "LVGI": 1.1,
        }.items()
    ]
    d = compute_distress(metrics)
    ben = d["models"]["beneish"]
    assert "m_score" in ben
    assert isinstance(ben["manipulation_suspect"], bool)


def test_compute_distress_zero_total_assets_is_safe():
    """总资产为 0 时不得触发除零，且相关模型判为不可用。"""
    metrics = [
        MetricValue(name=n, value=0.0)
        for n in ("总资产", "负债合计", "营运资金", "留存收益", "利润总额",
                  "所有者权益合计", "流动资产", "流动负债", "净利润")
    ]
    d = compute_distress(metrics)
    assert d["models"].get("altman") is None
    assert d["models"].get("ohlson") is None


def test_behavioral_event_value_types():
    """事件值支持 bool / int / str / 空串：命中才计分，不得崩。"""
    b = compute_behavioral(
        {"裁判文书": 3, "经营异常": "列入经营异常名录", "股权质押": "", "环保处罚": False}
    )
    assert b["scores"]["司法涉诉"] == 100.0  # 35*3 → clamp 100
    assert b["scores"]["经营异常"] == 25.0
    assert b["scores"]["股权风险"] == 0.0  # 空串视为未命中
    assert b["scores"]["行政处罚"] == 0.0  # False 视为未命中
