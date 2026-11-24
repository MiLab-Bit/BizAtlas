"""Independent binary risk evaluation metrics and split provenance.

Metrics are computed only on observed binary outcomes. Censored/unknown
records are excluded and counted, never silently coerced to non-events.
This evaluator cannot approve a model for empirical PD publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from typing import Sequence

from bizatlas.data.credit_events import LabelStatus


@dataclass(frozen=True)
class EvaluationObservation:
    entity_id: str
    group_id: str
    status: LabelStatus
    probability: float | None


@dataclass(frozen=True)
class EvaluationSummary:
    n_total: int
    n_observed: int
    n_positive: int
    n_negative: int
    n_censored: int
    n_unknown: int
    n_invalid_probability: int
    brier: float | None
    log_loss: float | None
    auc: float | None
    evaluation_status: str


def _auc(labels: list[int], probabilities: list[float]) -> float | None:
    positive = [p for y, p in zip(labels, probabilities) if y == 1]
    negative = [p for y, p in zip(labels, probabilities) if y == 0]
    if not positive or not negative:
        return None
    concordant = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p in positive for n in negative
    )
    return concordant / (len(positive) * len(negative))


def evaluate_binary_probabilities(
    observations: Sequence[EvaluationObservation],
    *,
    training_groups: frozenset[str],
    min_observed: int = 30,
) -> EvaluationSummary:
    """Evaluate on disjoint groups only; results are descriptive, not a gate."""
    if min_observed < 1:
        raise ValueError("min_observed must be positive")
    if any(row.group_id in training_groups for row in observations):
        raise ValueError("evaluation group overlaps training")
    if any(not row.entity_id or not row.group_id for row in observations):
        raise ValueError("missing evaluation identity")
    if len({row.entity_id for row in observations}) != len(observations):
        raise ValueError("duplicate evaluation entity")
    censored = sum(row.status is LabelStatus.RIGHT_CENSORED for row in observations)
    unknown = sum(row.status is LabelStatus.UNKNOWN for row in observations)
    labels: list[int] = []
    probabilities: list[float] = []
    invalid = 0
    for row in observations:
        if row.status not in (LabelStatus.POSITIVE, LabelStatus.NEGATIVE_OBSERVED):
            continue
        if row.probability is None or not isfinite(float(row.probability)):
            invalid += 1
            continue
        p = float(row.probability)
        if not 0.0 <= p <= 1.0:
            invalid += 1
            continue
        labels.append(int(row.status is LabelStatus.POSITIVE))
        probabilities.append(p)
    n = len(labels)
    ready = n >= min_observed and 0 < sum(labels) < n and invalid == 0
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / n if n else None
    eps = 1e-15
    log_loss = (
        -sum(
            y * log(max(eps, min(1 - eps, p)))
            + (1 - y) * log(max(eps, min(1 - eps, 1 - p)))
            for p, y in zip(probabilities, labels)
        ) / n if n else None
    )
    return EvaluationSummary(
        n_total=len(observations),
        n_observed=n,
        n_positive=sum(labels),
        n_negative=n - sum(labels),
        n_censored=censored,
        n_unknown=unknown,
        n_invalid_probability=invalid,
        brier=brier,
        log_loss=log_loss,
        auc=_auc(labels, probabilities),
        evaluation_status="METRICS_AVAILABLE" if ready else "INSUFFICIENT_EVIDENCE",
    )
