"""Application-service entrypoint for optional experimental risk inference.

Service inputs are already normalized provider facts with explicit evidence.
No model score can overwrite the existing rules-based risk decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bizatlas.contracts.models import RiskResult
from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.artifact_store import load_artifact
from bizatlas.risk.feature_bridge import FeatureObservation
from bizatlas.risk.model_catalog import read_model
from bizatlas.risk.scoring_bridge import enrich_with_experimental_model


@dataclass(frozen=True)
class ExperimentalModelRequest:
    model_id: str
    version: str
    observation_at: datetime
    features: tuple[FeatureObservation, ...]
    evidence: tuple[TemporalEvidence, ...]


def apply_registered_experimental_model(
    risk: RiskResult,
    request: ExperimentalModelRequest,
    *,
    manifest_directory: Path,
    artifact_directory: Path,
) -> RiskResult:
    """Opt-in application service; no automatic model activation."""
    manifest = read_model(manifest_directory, request.model_id, request.version)
    artifact = load_artifact(artifact_directory, manifest.artifact_sha256)
    return enrich_with_experimental_model(
        risk,
        manifest=manifest,
        artifact=artifact,
        observations=list(request.features),
        evidence=list(request.evidence),
        observation_at=request.observation_at,
    )
