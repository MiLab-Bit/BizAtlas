"""PD/LGD 校准层单测（P0-①）。"""
import math

from bizatlas.risk.calibration import (
    calibrate,
    logistic_pd,
    auc,
    ks,
    fit,
    CAL_A,
    CAL_B,
)


def test_logistic_pd_monotonic_and_bounded():
    p0 = logistic_pd(0)
    p50 = logistic_pd(50)
    p100 = logistic_pd(100)
    assert 0 < p0 < p50 < p100 < 1
    assert abs(p0 - logistic_pd(0, CAL_A, CAL_B)) < 1e-9


def test_calibrate_veto_caps_pd():
    res = calibrate({"score": 10, "veto": {"triggered": True, "reason": "失信"}})
    assert res.pd == 0.95
    assert res.calibrated_grade == "BLACK"


def test_calibrate_with_amount_computes_el():
    res = calibrate({"score": 50, "veto": {}}, applied_amount=1000.0, sector_risk="normal")
    assert res.ead == 1000.0
    assert res.expected_loss is not None
    # EL 在代码内用未四舍五入 pd 计算后取整；用四舍五入 pd 复算允许 0.05 舍入差
    assert abs(res.expected_loss - res.pd * res.lgd * 1000.0) < 0.05


def test_auc_perfect_separation():
    y = [0, 0, 1, 1]
    s = [0.1, 0.2, 0.8, 0.9]
    assert auc(y, s) == 1.0


def test_auc_ks_insufficient_labels_nan():
    assert math.isnan(auc([0, 0], [0.1, 0.2]))
    assert math.isnan(ks([1, 1], [0.1, 0.2]))


def test_fit_returns_prior_when_no_labels():
    out = fit([0], [0.5])
    assert out["a"] == CAL_A and out["b"] == CAL_B


def test_ks_range():
    y = [0, 0, 1, 1]
    s = [0.1, 0.2, 0.8, 0.9]
    k = ks(y, s)
    assert 0.0 <= k <= 1.0
