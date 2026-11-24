"""Deterministic, dependency-free logistic ranking model.

Offline training only. The sigmoid output is an unvalidated model estimate,
NOT a publishable probability of default. A separate independent validation
and release authorization are required before any empirical PD publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class TrainingRow:
    entity_id: str
    group_id: str
    features: Mapping[str, float]
    label: int


@dataclass(frozen=True)
class LogisticArtifact:
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    n_rows: int
    n_positive: int
    iterations: int
    artifact_sha256: str

    def score(self, features: Mapping[str, float]) -> float:
        if set(features) != set(self.feature_names):
            raise ValueError("inference feature schema mismatch")
        values = [float(features[name]) for name in self.feature_names]
        if any(not math.isfinite(value) for value in values):
            raise ValueError("nonfinite inference feature")
        z = self.intercept + sum(
            weight * (value - mean) / scale
            for weight, value, mean, scale in zip(
                self.coefficients, values, self.means, self.scales
            )
        )
        # Stable sigmoid; ranking score only, no PD claim.
        return _sigmoid(z)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def train_logistic(
    rows: Sequence[TrainingRow],
    feature_names: tuple[str, ...],
    *,
    iterations: int = 400,
    learning_rate: float = 0.08,
    l2: float = 0.01,
) -> LogisticArtifact:
    """Fit standardized logistic regression using full-batch gradient descent.

    Explicitly rejects unobserved labels, schema drift, duplicate entities,
    nonfinite inputs, and single-class datasets. Training-group segregation
    is enforced upstream by the cohort splitter.
    """
    if len(rows) < 20 or len({row.label for row in rows}) != 2:
        raise ValueError("at least 20 observed rows and both classes required")
    if len(set(feature_names)) != len(feature_names) or not feature_names:
        raise ValueError("unique nonempty feature names required")
    if any(not name for name in feature_names):
        raise ValueError("empty feature name")
    if iterations < 1 or iterations > 100000:
        raise ValueError("invalid iterations")
    if not (math.isfinite(learning_rate) and 0 < learning_rate <= 1):
        raise ValueError("invalid learning rate")
    if not (math.isfinite(l2) and l2 >= 0):
        raise ValueError("invalid regularization")
    if len({row.entity_id for row in rows}) != len(rows):
        raise ValueError("duplicate training entity")
    if any(not row.entity_id or not row.group_id for row in rows):
        raise ValueError("missing entity or group")
    if any(row.label not in (0, 1) for row in rows):
        raise ValueError("only observed binary labels supported")
    if any(set(row.features) != set(feature_names) for row in rows):
        raise ValueError("training feature schema mismatch")
    matrix = [[float(row.features[name]) for name in feature_names] for row in rows]
    if any(not math.isfinite(value) for values in matrix for value in values):
        raise ValueError("nonfinite training feature")
    n = len(rows)
    d = len(feature_names)
    means = tuple(sum(row[j] for row in matrix) / n for j in range(d))
    scales = tuple(
        max(1e-8, math.sqrt(sum((row[j] - means[j]) ** 2 for row in matrix) / n))
        for j in range(d)
    )
    standardized = [
        [(row[j] - means[j]) / scales[j] for j in range(d)]
        for row in matrix
    ]
    positive = sum(row.label for row in rows)
    intercept = math.log(positive / (n - positive))
    weights = [0.0] * d
    for _ in range(iterations):
        errors = [
            _sigmoid(intercept + sum(w * x for w, x in zip(weights, features)))
            - row.label
            for features, row in zip(standardized, rows)
        ]
        intercept -= learning_rate * sum(errors) / n
        for j in range(d):
            gradient = sum(error * x[j] for error, x in zip(errors, standardized)) / n
            weights[j] -= learning_rate * (gradient + l2 * weights[j])
        if not math.isfinite(intercept) or any(not math.isfinite(w) for w in weights):
            raise ValueError("training diverged")
    canonical = {
        "feature_names": feature_names,
        "means": means,
        "scales": scales,
        "coefficients": tuple(weights),
        "intercept": intercept,
        "n_rows": n,
        "n_positive": positive,
        "iterations": iterations,
    }
    digest = sha256(json.dumps(canonical, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return LogisticArtifact(
        feature_names, means, scales, tuple(weights), intercept,
        n, positive, iterations, digest
    )
