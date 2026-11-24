"""Compatibility entrypoint for logistic point-in-time inference.

The shared inference path is authoritative for Logistic and GBDT alike.
"""
from __future__ import annotations

from datetime import datetime

from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.feature_bridge import FeatureObservation
from bizatlas.risk.logistic_model import LogisticArtifact
from bizatlas.risk.model_inference import infer_model_as_of
from bizatlas.risk.model_registry import ModelInference, ModelManifest


def infer_logistic_as_of(
    manifest: ModelManifest,
    artifact: LogisticArtifact,
    features: list[FeatureObservation],
    evidence: list[TemporalEvidence],
    observation_at: datetime,
) -> ModelInference:
    return infer_model_as_of(manifest, artifact, features, evidence, observation_at)
