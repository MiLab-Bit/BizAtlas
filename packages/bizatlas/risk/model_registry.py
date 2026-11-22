"""Versioned risk-model contracts and conservative inference admission.

Registration records model metadata; it does not certify empirical PD.
An unverified model may produce a ranking score, never a published PD.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Mapping


class ModelFamily(str, Enum):
    RULES = "RULES"
    LOGISTIC = "LOGISTIC"
    GBDT = "GBDT"


class ModelLifecycle(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    HOLDOUT_PENDING = "HOLDOUT_PENDING"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    unit: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("feature name required")


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    version: str
    family: ModelFamily
    lifecycle: ModelLifecycle
    feature_schema: tuple[FeatureSpec, ...]
    artifact_sha256: str
    training_cutoff: datetime | None
    label_definition: str
    training_dataset_id: str

    def __post_init__(self) -> None:
        if not self.model_id or not self.version or not self.label_definition:
            raise ValueError("model id, version and label definition required")
        if len(self.artifact_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.artifact_sha256.lower()
        ):
            raise ValueError("model artifact must have SHA256")
        names = [f.name for f in self.feature_schema]
        if len(names) != len(set(names)):
            raise ValueError("duplicate feature names")
        if self.training_cutoff is not None and (
            self.training_cutoff.tzinfo is None
            or self.training_cutoff.utcoffset() is None
        ):
            raise ValueError("training cutoff requires timezone")


@dataclass(frozen=True)
class ModelInference:
    model_id: str
    model_version: str
    ranking_score: float | None
    empirical_pd: None
    status: str
    missing_features: tuple[str, ...]
    reason: str


def admit_model_inference(
    manifest: ModelManifest,
    features: Mapping[str, float | None],
    *,
    observation_at: datetime,
    ranking_score: float | None,
) -> ModelInference:
    """Reject invalid inputs and never infer calibration from model family."""
    if observation_at.tzinfo is None or observation_at.utcoffset() is None:
        raise ValueError("observation time requires timezone")
    if manifest.training_cutoff is not None and (
        observation_at.astimezone(timezone.utc)
        <= manifest.training_cutoff.astimezone(timezone.utc)
    ):
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", (), "observation_not_after_training_cutoff"
        )
    missing = tuple(
        spec.name for spec in manifest.feature_schema
        if spec.required and (
            spec.name not in features or features[spec.name] is None
        )
    )
    if missing:
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", missing, "required_features_missing"
        )
    if any(
        value is not None and not isfinite(float(value))
        for value in features.values()
    ):
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", (), "nonfinite_features"
        )
    if manifest.lifecycle is ModelLifecycle.RETIRED:
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", (), "retired_model"
        )
    if ranking_score is None or not isfinite(float(ranking_score)):
        return ModelInference(
            manifest.model_id, manifest.version, None, None,
            "ABSTAIN", (), "invalid_model_score"
        )
    return ModelInference(
        manifest.model_id, manifest.version, float(ranking_score), None,
        "RANKING_ONLY", (), "empirical_calibration_not_authorized"
    )
