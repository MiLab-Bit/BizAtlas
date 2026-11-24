"""Offline training and immutable registration from an approved snapshot.

This workflow accepts a preconstructed snapshot only. It does not claim to
verify source licenses, event labels or temporal provenance on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bizatlas.risk.artifact_store import save_artifact
from bizatlas.risk.gbdt_model import train_gbdt
from bizatlas.risk.logistic_model import train_logistic
from bizatlas.risk.model_catalog import register_model
from bizatlas.risk.model_registry import FeatureSpec, ModelFamily, ModelLifecycle, ModelManifest
from bizatlas.risk.snapshot_store import load_training_snapshot


@dataclass(frozen=True)
class TrainingRegistration:
    model_id: str
    version: str
    dataset_id: str
    artifact_sha256: str
    family: ModelFamily
    lifecycle: ModelLifecycle


def train_and_register(
    *,
    snapshot_id: str,
    model_id: str,
    version: str,
    family: ModelFamily,
    snapshot_directory: Path,
    artifact_directory: Path,
    manifest_directory: Path,
    feature_units: dict[str, str],
) -> TrainingRegistration:
    """Create experimental artifacts without activating a model in production."""
    if family not in (ModelFamily.LOGISTIC, ModelFamily.GBDT):
        raise ValueError("only trained Logistic and GBDT families supported")
    if not model_id.strip() or not version.strip():
        raise ValueError("model identity required")
    snapshot = load_training_snapshot(snapshot_directory, snapshot_id)
    if set(feature_units) != set(snapshot.feature_names):
        raise ValueError("feature unit schema mismatch")
    if any(not unit.strip() for unit in feature_units.values()):
        raise ValueError("feature units must be declared")
    if snapshot.n_positive == 0 or snapshot.n_positive == len(snapshot.rows):
        raise ValueError("training requires both observed classes")
    artifact = (
        train_logistic(snapshot.rows, snapshot.feature_names)
        if family is ModelFamily.LOGISTIC
        else train_gbdt(snapshot.rows, snapshot.feature_names)
    )
    manifest = ModelManifest(
        model_id=model_id,
        version=version,
        family=family,
        lifecycle=ModelLifecycle.EXPERIMENTAL,
        feature_schema=tuple(
            FeatureSpec(name=name, unit=feature_units[name])
            for name in snapshot.feature_names
        ),
        artifact_sha256=artifact.artifact_sha256,
        training_cutoff=snapshot.observation_cutoff,
        label_definition=snapshot.label_definition,
        training_dataset_id=snapshot.snapshot_id,
    )
    # Persist artifact before publishing its manifest. An interrupted write
    # leaves an unreferenced artifact, never a manifest with no artifact.
    save_artifact(artifact_directory, artifact)
    register_model(manifest_directory, manifest)
    return TrainingRegistration(
        model_id, version, snapshot.snapshot_id,
        artifact.artifact_sha256, family, ModelLifecycle.EXPERIMENTAL
    )
