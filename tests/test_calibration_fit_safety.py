"""Synthetic regression tests; no evidence of real-world calibration."""
from bizatlas.risk.calibration import CAL_A, CAL_B, fit, logistic_pd


def test_fit_does_not_optimize_auc_intercept():
    # 100 rows, monotonic score, 20 positives at high score.
    labels = [0] * 80 + [1] * 20
    scores = [float(i) for i in range(100)]
    result = fit(labels, scores)
    assert "brier_train" in result
    assert "auc" not in result
    assert result["note"] == "in_sample_fit_only; independent_holdout_required"
    prior_loss = sum(
        (logistic_pd(s, CAL_A, CAL_B) - y) ** 2
        for s, y in zip(scores, labels)
    ) / len(labels)
    assert result["brier_train"] <= prior_loss


def test_fit_rejects_tiny_or_single_class_samples():
    assert "prior_only" in fit([0] * 19, [1.0] * 19)["note"]
    assert "prior_only" in fit([0] * 20, [1.0] * 20)["note"]


def test_fit_rejects_length_mismatch_and_nonfinite():
    assert "prior_only" in fit([0, 1] * 10, [1.0])["note"]
    assert "prior_only" in fit([0, 1] * 10, [float("nan")] * 20)["note"]
