"""Unified evidence-gated inference for Logistic and experimental GBDT.

No trained-model score is interpreted or serialized as empirical PD.
"""
from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.feature_bridge import FeatureObservation, assemble_features_as_of
from bizatlas.risk.gbdt_model import GBDTArtifact
from bizatlas.risk.logistic_model import LogisticArtifact
from bizatlas.risk.model_registry import (
    ModelFamily,
    ModelInference,
    ModelManifest,
    admit_model_inference,
)

ModelArtifact: TypeAlias = LogisticArtifact | GBDTArtifact


def infer_model_as_of(
    manifest: ModelManifest,
    artifact: ModelArtifact,
    observations: list[FeatureObservation],
    evidence: list[TemporalEvidence],
    observation_at: datetime,
) -> ModelInference:
    if manifest.family is ModelFamily.LOGISTIC and not isinstance(artifact, LogisticArtifact):
        raise ValueError("manifest/artifact family mismatch")
    if manifest.family is ModelFamily.GBDT and not isinstance(artifact, GBDTArtifact):
        raise ValueError("manifest/artifact family mismatch")
    if manifest.family not in (ModelFamily.LOGISTIC, ModelFamily.GBDT):
        raise ValueError("unsupported trained model family")
    if manifest.artifact_sha256 != artifact.artifact_sha256:
        raise ValueError("model artifact digest mismatch")
    if tuple(spec.name for spec in manifest.feature_schema) != artifact.feature_names:
        raise ValueError("model feature order mismatch")

    assembled = assemble_features_as_of(
        manifest, observations, evidence, observation_at
    )
    if not assembled.admissible:
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", (), assembled.reason
        )
    if any(value is None for value in assembled.values.values()):
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN",
            tuple(name for name, value in assembled.values.items() if value is None),
            "missing_feature_without_imputation",
        )
    # Gate retirement and temporal compatibility before executing the model.
    preflight = admit_model_inference(
        manifest, assembled.values, observation_at=observation_at, ranking_score=None
    )
    if preflight.reason != "invalid_model_score":
        return preflight
    score = artifact.score({
        name: float(value) for name, value in assembled.values.items()
        if value is not None
    })
    return admit_model_inference(
        manifest, assembled.values, observation_at=observation_at, ranking_score=score
    )
