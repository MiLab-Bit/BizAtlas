"""Bridge point-in-time admitted evidence to versioned model inputs.

A feature value without a resolvable, authorized evidence reference is not
eligible for model inference, even if the numeric value is present.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from bizatlas.data.temporal_evidence import (
    EvidenceDecision,
    TemporalEvidence,
    eligible_as_of,
)
from bizatlas.risk.model_registry import ModelManifest


@dataclass(frozen=True)
class FeatureObservation:
    name: str
    value: float | None
    evidence_id: str
    unit: str


@dataclass(frozen=True)
class FeatureAssembly:
    values: dict[str, float | None]
    admissible: bool
    reason: str
    excluded_evidence: dict[str, str]


def assemble_features_as_of(
    manifest: ModelManifest,
    observations: list[FeatureObservation],
    evidence: list[TemporalEvidence],
    observation_at: datetime,
) -> FeatureAssembly:
    """Reject duplicate features, mismatched units and hindsight leakage."""
    by_evidence = {item.evidence_id: item for item in evidence}
    if len(by_evidence) != len(evidence):
        return FeatureAssembly({}, False, "duplicate_evidence_id", {})
    by_name: dict[str, FeatureObservation] = {}
    for item in observations:
        if item.name in by_name:
            return FeatureAssembly({}, False, "duplicate_feature_name", {})
        by_name[item.name] = item
    required = {spec.name: spec for spec in manifest.feature_schema}
    unexpected = set(by_name) - set(required)
    if unexpected:
        return FeatureAssembly({}, False, "unexpected_features", {})
    missing = [
        spec.name for spec in manifest.feature_schema
        if spec.required and (
            spec.name not in by_name or by_name[spec.name].value is None
        )
    ]
    if missing:
        return FeatureAssembly({}, False, "missing_required_features", {})
    if any(
        item.unit != required[item.name].unit
        for item in observations
    ):
        return FeatureAssembly({}, False, "feature_unit_mismatch", {})
    if any(item.evidence_id not in by_evidence for item in observations):
        return FeatureAssembly({}, False, "unresolved_feature_evidence", {})
    selected_ids = {item.evidence_id for item in observations}
    _, decisions = eligible_as_of(
        [by_evidence[eid] for eid in sorted(selected_ids)], observation_at
    )
    excluded = {
        eid: decision.value for eid, decision in decisions.items()
        if decision is not EvidenceDecision.ADMISSIBLE
    }
    if excluded:
        return FeatureAssembly({}, False, "inadmissible_point_in_time_evidence", excluded)
    if any(
        item.value is not None and not isfinite(float(item.value))
        for item in observations
    ):
        return FeatureAssembly({}, False, "nonfinite_feature", {})
    return FeatureAssembly(
        {name: by_name[name].value if name in by_name else None
         for name in required},
        True, "admitted", {}
    )
