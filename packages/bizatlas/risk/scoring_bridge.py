"""Attach an experimental model ranking to an existing RiskResult.

The original rules-based grade, decision and score remain authoritative.
Experimental scores are diagnostic metadata, never a PD or credit decision.
"""
from __future__ import annotations

from datetime import datetime

from bizatlas.contracts.models import RiskResult
from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.feature_bridge import FeatureObservation
from bizatlas.risk.model_inference import ModelArtifact, infer_model_as_of
from bizatlas.risk.model_registry import ModelManifest


def enrich_with_experimental_model(
    risk: RiskResult,
    *,
    manifest: ModelManifest,
    artifact: ModelArtifact,
    observations: list[FeatureObservation],
    evidence: list[TemporalEvidence],
    observation_at: datetime,
) -> RiskResult:
    """Return a copy with non-decisional model metadata.

    This is an explicit opt-in bridge. It does not change score, grade,
    ratability, veto, PD, master scale or the credit decision.
    """
    inference = infer_model_as_of(
        manifest, artifact, observations, evidence, observation_at
    )
    result = risk.model_copy(deep=True)
    modules = dict(result.modules or {})
    modules["experimental_model"] = {
        "model_id": inference.model_id,
        "model_version": inference.model_version,
        "family": manifest.family.value,
        "lifecycle": manifest.lifecycle.value,
        "artifact_sha256": manifest.artifact_sha256,
        "status": inference.status,
        "reason": inference.reason,
        "missing_features": list(inference.missing_features),
        "ranking_score": inference.ranking_score,
        "empirical_pd": None,
        "decision_authority": False,
        "disclosure": "实验性排序信号，未通过独立概率校准与授信决策验证",
    }
    result.modules = modules
    return result
