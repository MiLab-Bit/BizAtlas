"""Minimal deterministic gradient-boosted decision-stump risk ranker.

This is a dependency-free experimental GBDT baseline, not XGBoost or
LightGBM. It fits logistic residuals with squared-error stumps and shrinkage.
The sigmoid score is an unvalidated ranking signal, never empirical PD.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence

from bizatlas.risk.logistic_model import TrainingRow, _sigmoid


@dataclass(frozen=True)
class DecisionStump:
    feature_index: int
    threshold: float
    left_value: float
    right_value: float

    def predict(self, values: tuple[float, ...]) -> float:
        return self.left_value if values[self.feature_index] <= self.threshold else self.right_value


@dataclass(frozen=True)
class GBDTArtifact:
    feature_names: tuple[str, ...]
    intercept: float
    learning_rate: float
    trees: tuple[DecisionStump, ...]
    n_rows: int
    n_positive: int
    artifact_sha256: str

    def score(self, features: Mapping[str, float]) -> float:
        if set(features) != set(self.feature_names):
            raise ValueError("inference feature schema mismatch")
        values = tuple(float(features[name]) for name in self.feature_names)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("nonfinite inference feature")
        z = self.intercept + self.learning_rate * sum(
            tree.predict(values) for tree in self.trees
        )
        return _sigmoid(z)


def _fit_stump(
    matrix: list[tuple[float, ...]],
    residuals: list[float],
    *,
    min_leaf: int,
    l2: float,
) -> DecisionStump | None:
    n, d = len(matrix), len(matrix[0])
    best: tuple[float, int, float, float, float] | None = None
    for feature_index in range(d):
        ordered = sorted(
            ((row[feature_index], residuals[i]) for i, row in enumerate(matrix)),
            key=lambda item: item[0],
        )
        prefix = [0.0]
        prefix_sq = [0.0]
        for _, residual in ordered:
            prefix.append(prefix[-1] + residual)
            prefix_sq.append(prefix_sq[-1] + residual * residual)
        for k in range(min_leaf, n - min_leaf + 1):
            if ordered[k - 1][0] >= ordered[k][0]:
                continue
            nl, nr = k, n - k
            sl, sr = prefix[k], prefix[n] - prefix[k]
            left = sl / (nl + l2)
            right = sr / (nr + l2)
            loss = (
                prefix_sq[k] - 2 * left * sl + nl * left * left
                + prefix_sq[n] - prefix_sq[k] - 2 * right * sr + nr * right * right
                + l2 * (left * left + right * right)
            )
            threshold = ordered[k - 1][0] + (ordered[k][0] - ordered[k - 1][0]) / 2
            candidate = (loss, feature_index, threshold, left, right)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    _, feature_index, threshold, left, right = best
    return DecisionStump(feature_index, threshold, left, right)


def train_gbdt(
    rows: Sequence[TrainingRow],
    feature_names: tuple[str, ...],
    *,
    n_estimators: int = 80,
    learning_rate: float = 0.1,
    min_leaf: int = 5,
    l2: float = 1.0,
) -> GBDTArtifact:
    if len(rows) < 20 or len({row.label for row in rows}) != 2:
        raise ValueError("at least 20 observed rows and both classes required")
    if not feature_names or len(feature_names) != len(set(feature_names)):
        raise ValueError("unique nonempty feature names required")
    if any(not name for name in feature_names):
        raise ValueError("empty feature name")
    if len({row.entity_id for row in rows}) != len(rows):
        raise ValueError("duplicate training entity")
    if any(not row.entity_id or not row.group_id for row in rows):
        raise ValueError("missing entity or group")
    if any(row.label not in (0, 1) for row in rows):
        raise ValueError("only observed binary labels supported")
    if any(set(row.features) != set(feature_names) for row in rows):
        raise ValueError("training feature schema mismatch")
    if not 1 <= n_estimators <= 10000:
        raise ValueError("invalid n_estimators")
    if not (math.isfinite(learning_rate) and 0 < learning_rate <= 1):
        raise ValueError("invalid learning rate")
    if not (math.isfinite(l2) and l2 >= 0):
        raise ValueError("invalid l2")
    if min_leaf < 1 or 2 * min_leaf > len(rows):
        raise ValueError("invalid min_leaf")
    matrix = [tuple(float(row.features[name]) for name in feature_names) for row in rows]
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ValueError("nonfinite training feature")
    positive = sum(row.label for row in rows)
    intercept = math.log(positive / (len(rows) - positive))
    logits = [intercept] * len(rows)
    trees: list[DecisionStump] = []
    for _ in range(n_estimators):
        residuals = [
            row.label - _sigmoid(logit)
            for row, logit in zip(rows, logits)
        ]
        stump = _fit_stump(matrix, residuals, min_leaf=min_leaf, l2=l2)
        if stump is None:
            break
        trees.append(stump)
        logits = [
            logit + learning_rate * stump.predict(features)
            for logit, features in zip(logits, matrix)
        ]
    canonical = {
        "feature_names": feature_names,
        "intercept": intercept,
        "learning_rate": learning_rate,
        "trees": [
            (t.feature_index, t.threshold, t.left_value, t.right_value)
            for t in trees
        ],
        "n_rows": len(rows),
        "n_positive": positive,
    }
    digest = sha256(json.dumps(canonical, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return GBDTArtifact(
        feature_names, intercept, learning_rate, tuple(trees),
        len(rows), positive, digest
    )
