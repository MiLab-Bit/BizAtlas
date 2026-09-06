"""补充覆盖：连续亏损识别 / 校准层拟合与主标尺边界（B-RCF v2.0.1）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import MetricValue, RuleHit
from bizatlas.risk.calibration import (
    MASTER_SCALE,
    fit,
    logistic_pd,
    master_scale_from_pd,
)
from bizatlas.risk.score import _detect_consecutive_loss


def test_detect_consecutive_loss_by_metric():
    metrics = [MetricValue(name="连续亏损年数", value=3.0)]
    hit, reason = _detect_consecutive_loss(metrics, {}, [])
    assert hit is True
    assert "连续亏损年数" in reason


def test_detect_consecutive_loss_by_event():
    hit, reason = _detect_consecutive_loss([], {"连续两年扣非净利为负": True}, [])
    assert hit is True
    assert "连续两年扣非净利为负" in reason


def test_detect_consecutive_loss_by_rule():
    hits = [
        RuleHit(rule_id="R1011", name="亏损预警", dimension="财务",
                severity="高", message="连续亏损")
    ]
    hit, reason = _detect_consecutive_loss([], {}, hits)
    assert hit is True
    assert "R1011" in reason


def test_detect_consecutive_loss_tolerates_bad_value():
    """指标值不可解析时不得抛异常（数据铁律：脏数据优雅降级）。"""
    metrics = [MetricValue(name="连续亏损年数", value=None)]
    hit, _ = _detect_consecutive_loss(metrics, {}, [])
    assert hit is False


def test_detect_consecutive_loss_none():
    assert _detect_consecutive_loss([], {}, []) == (False, "")


def test_logistic_pd_monotonic_and_bounded():
    vals = [logistic_pd(s) for s in (0.0, 25.0, 50.0, 75.0, 100.0)]
    assert all(0.0 < v < 1.0 for v in vals)
    assert vals == sorted(vals), "分数越高 PD 必须越高"


def test_master_scale_monotonic_with_pd():
    scales = [s for s, _, _ in MASTER_SCALE]
    assert scales, "主标尺档位表不得为空"
    low = master_scale_from_pd(0.001)
    high = master_scale_from_pd(0.99)
    assert low != high
    assert scales.index(low) < scales.index(high), "PD 越高主标尺档位越差"


def test_fit_requires_two_classes():
    out = fit([0, 0, 0], [10.0, 20.0, 30.0])
    assert out["a"] == -6.2 and "标签不足" in out["note"]


def test_fit_estimates_coefficients():
    y_true = [0, 0, 0, 1, 1, 1]
    y_score = [10.0, 20.0, 30.0, 70.0, 80.0, 95.0]
    out = fit(y_true, y_score)
    assert "auc" in out
    assert 0.0 <= out["auc"] <= 1.0
    assert out["auc"] > 0.8, "完全可分样本上 AUC 应接近 1"
