"""Append-only model manifest catalog, isolated from model binary artifacts.

Registration never grants production release or empirical PD publication.
The catalog refuses replacing a version with a different manifest.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import json
import os
from tempfile import NamedTemporaryFile

from bizatlas.risk.model_registry import FeatureSpec, ModelFamily, ModelLifecycle, ModelManifest


def _manifest_payload(manifest: ModelManifest) -> dict:
    return {
        "model_id": manifest.model_id,
        "version": manifest.version,
        "family": manifest.family.value,
        "lifecycle": manifest.lifecycle.value,
        "feature_schema": [asdict(spec) for spec in manifest.feature_schema],
        "artifact_sha256": manifest.artifact_sha256,
        "training_cutoff": (
            manifest.training_cutoff.isoformat() if manifest.training_cutoff else None
        ),
        "label_definition": manifest.label_definition,
        "training_dataset_id": manifest.training_dataset_id,
    }


def register_model(root: Path, manifest: ModelManifest) -> Path:
    """Persist a versioned manifest under a digest-derived filename."""
    from hashlib import sha256

    if not manifest.training_dataset_id:
        raise ValueError("training dataset snapshot id required")
    payload = _manifest_payload(manifest)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    identity = sha256(f"{manifest.model_id}\0{manifest.version}".encode()).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    target = root / (identity + ".json")
    if target.exists():
        if target.read_bytes() != blob:
            raise ValueError("model version already registered with different content")
        return target
    with NamedTemporaryFile(mode="wb", dir=root, prefix=".manifest-", delete=False) as tmp:
        tmp.write(blob)
        temp_name = tmp.name
    try:
        try:
            os.link(temp_name, target)
        except FileExistsError:
            if target.read_bytes() != blob:
                raise ValueError("concurrent model version conflict")
    finally:
        os.unlink(temp_name)
    return target


def read_model(root: Path, model_id: str, version: str) -> ModelManifest:
    from hashlib import sha256

    identity = sha256(f"{model_id}\0{version}".encode()).hexdigest()
    payload = json.loads((root / (identity + ".json")).read_text(encoding="utf-8"))
    if payload["model_id"] != model_id or payload["version"] != version:
        raise ValueError("model identity mismatch")
    cutoff = (
        datetime.fromisoformat(payload["training_cutoff"])
        if payload["training_cutoff"] else None
    )
    return ModelManifest(
        model_id=payload["model_id"],
        version=payload["version"],
        family=ModelFamily(payload["family"]),
        lifecycle=ModelLifecycle(payload["lifecycle"]),
        feature_schema=tuple(FeatureSpec(**item) for item in payload["feature_schema"]),
        artifact_sha256=payload["artifact_sha256"],
        training_cutoff=cutoff,
        label_definition=payload["label_definition"],
        training_dataset_id=payload["training_dataset_id"],
    )
