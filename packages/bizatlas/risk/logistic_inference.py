"""Connect a fitted logistic artifact to the existing model admission gate.

The artifact hash and feature schema must match the manifest exactly.
Inference returns RANKING_ONLY; no path publishes empirical PD.
"""
from __future__ import annotations

from datetime import datetime

from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.feature_bridge import FeatureObservation, assemble_features_as_of
from bizatlas.risk.logistic_model import LogisticArtifact
from bizatlas.risk.model_registry import (
    ModelFamily,
    ModelInference,
    ModelManifest,
    admit_model_inference,
)


def infer_logistic_as_of(
    manifest: ModelManifest,
    artifact: LogisticArtifact,
    features: list[FeatureObservation],
    evidence: list[TemporalEvidence],
    observation_at: datetime,
) -> ModelInference:
    if manifest.family is not ModelFamily.LOGISTIC:
        raise ValueError("manifest must declare LOGISTIC family")
    if manifest.artifact_sha256 != artifact.artifact_sha256:
        raise ValueError("model artifact digest mismatch")
    if tuple(spec.name for spec in manifest.feature_schema) != artifact.feature_names:
        raise ValueError("model feature order mismatch")
    assembled = assemble_features_as_of(manifest, features, evidence, observation_at)
    if not assembled.admissible:
        return ModelInference(
            manifest.model_id, manifest.version, None, None, "ABSTAIN",
            (), assembled.reason
        )
    admitted = admit_model_inference(
        manifest, assembled.values, observation_at=observation_at, ranking_score=None
    )
    # The manifest gate must run before computing a ranking score.
    # A missing ranking score is the only expected pre-inference rejection.
    if admitted.reason != "invalid_model_score":
        return admitted
    score = artifact.score({
        name: float(value) for name, value in assembled.values.items()
        if value is not None
    })
    return admit_model_inference(
        manifest, assembled.values, observation_at=observation_at, ranking_score=score
    )
