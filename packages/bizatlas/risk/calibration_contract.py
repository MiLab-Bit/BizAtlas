"""Fail-closed probability publication contract.

This module does not fit or validate a probability model. It prevents
unverified heuristic scores from being represented as empirical PDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from math import isfinite


class ProbabilityStatus(str, Enum):
    UNRATED = "UNRATED"
    PRIOR_ONLY = "PRIOR_ONLY"
    VALIDATED = "VALIDATED"


@dataclass(frozen=True)
class ProbabilityEvidence:
    """Validation metadata; must come from an independent evaluation gate."""

    label_definition: str | None = None
    calibration_version: str | None = None
    observation_end: date | None = None
    holdout_end: date | None = None
    point_in_time_audited: bool = False
    authorized_data: bool = False
    independent_holdout_passed: bool = False
    sufficient_label_followup: bool = False


@dataclass(frozen=True)
class ProbabilityPublication:
    status: ProbabilityStatus
    pd: float | None
    reason: str
    can_publish_as_empirical_pd: bool


def assess_probability_publication(
    candidate_pd: float | None,
    evidence: ProbabilityEvidence | None = None,
) -> ProbabilityPublication:
    """Require all empirical gates; missing evidence never means zero risk.

    A finite prior may be retained for explicitly labeled internal scenarios,
    but is never published as a validated default probability.
    """
    if candidate_pd is None:
        return ProbabilityPublication(
            ProbabilityStatus.UNRATED, None, "no_probability_estimate", False
        )
    if not isfinite(candidate_pd) or not 0.0 <= candidate_pd <= 1.0:
        return ProbabilityPublication(
            ProbabilityStatus.UNRATED, None, "invalid_probability", False
        )
    if evidence is None:
        return ProbabilityPublication(
            ProbabilityStatus.PRIOR_ONLY, candidate_pd, "no_validation_evidence", False
        )
    checks = (
        bool(evidence.label_definition),
        bool(evidence.calibration_version),
        evidence.observation_end is not None,
        evidence.holdout_end is not None,
        evidence.point_in_time_audited,
        evidence.authorized_data,
        evidence.independent_holdout_passed,
        evidence.sufficient_label_followup,
    )
    if not all(checks):
        return ProbabilityPublication(
            ProbabilityStatus.PRIOR_ONLY, candidate_pd, "validation_gate_incomplete", False
        )
    if evidence.holdout_end <= evidence.observation_end:
        return ProbabilityPublication(
            ProbabilityStatus.PRIOR_ONLY, candidate_pd, "invalid_holdout_chronology", False
        )
    return ProbabilityPublication(
        ProbabilityStatus.VALIDATED, candidate_pd, "validation_evidence_supplied", True
    )
