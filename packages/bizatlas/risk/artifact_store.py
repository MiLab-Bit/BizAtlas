"""Content-addressed model artifact persistence (offline, no pickle).

Writes are atomic and immutable. Model hashes are checked on loading. Only
explicit LogisticArtifact/GBDTArtifact structures are accepted.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from bizatlas.risk.gbdt_model import DecisionStump, GBDTArtifact
from bizatlas.risk.logistic_model import LogisticArtifact
from bizatlas.risk.model_inference import ModelArtifact


def _canonical_artifact(artifact: ModelArtifact) -> dict:
    if isinstance(artifact, LogisticArtifact):
        return {
            "feature_names": artifact.feature_names,
            "means": artifact.means,
            "scales": artifact.scales,
            "coefficients": artifact.coefficients,
            "intercept": artifact.intercept,
            "n_rows": artifact.n_rows,
            "n_positive": artifact.n_positive,
            "iterations": artifact.iterations,
        }
    if isinstance(artifact, GBDTArtifact):
        return {
            "feature_names": artifact.feature_names,
            "intercept": artifact.intercept,
            "learning_rate": artifact.learning_rate,
            "trees": [
                (t.feature_index, t.threshold, t.left_value, t.right_value)
                for t in artifact.trees
            ],
            "n_rows": artifact.n_rows,
            "n_positive": artifact.n_positive,
        }
    raise TypeError("unsupported model artifact")


def _digest(artifact: ModelArtifact) -> str:
    payload = _canonical_artifact(artifact)
    return sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _encode(artifact: ModelArtifact) -> bytes:
    if _digest(artifact) != artifact.artifact_sha256:
        raise ValueError("artifact internal digest mismatch")
    family = "LOGISTIC" if isinstance(artifact, LogisticArtifact) else "GBDT"
    envelope = {
        "schema_version": 1,
        "family": family,
        "artifact_sha256": artifact.artifact_sha256,
        "payload": _canonical_artifact(artifact),
    }
    return json.dumps(envelope, sort_keys=True, allow_nan=False).encode("utf-8")


def save_artifact(root: Path, artifact: ModelArtifact) -> Path:
    """Write one content-addressed JSON artifact; never overwrite existing data."""
    blob = _encode(artifact)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (artifact.artifact_sha256 + ".json")
    if target.exists():
        if target.read_bytes() != blob:
            raise ValueError("existing artifact content mismatch")
        return target
    with NamedTemporaryFile(mode="wb", dir=root, prefix=".artifact-", delete=False) as tmp:
        tmp.write(blob)
        temp_name = tmp.name
    try:
        # Atomic hard link fails if another writer has already created the key.
        try:
            os.link(temp_name, target)
        except FileExistsError:
            if target.read_bytes() != blob:
                raise ValueError("concurrent artifact content mismatch")
    finally:
        os.unlink(temp_name)
    return target


def load_artifact(root: Path, digest: str) -> ModelArtifact:
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid artifact digest")
    envelope = json.loads((root / (digest + ".json")).read_text(encoding="utf-8"))
    if envelope.get("schema_version") != 1 or envelope.get("artifact_sha256") != digest:
        raise ValueError("invalid artifact envelope")
    payload = envelope["payload"]
    family = envelope.get("family")
    if family == "LOGISTIC":
        artifact: ModelArtifact = LogisticArtifact(
            tuple(payload["feature_names"]), tuple(payload["means"]),
            tuple(payload["scales"]), tuple(payload["coefficients"]),
            payload["intercept"], payload["n_rows"], payload["n_positive"],
            payload["iterations"], digest,
        )
    elif family == "GBDT":
        artifact = GBDTArtifact(
            tuple(payload["feature_names"]), payload["intercept"],
            payload["learning_rate"],
            tuple(DecisionStump(*tree) for tree in payload["trees"]),
            payload["n_rows"], payload["n_positive"], digest,
        )
    else:
        raise ValueError("unsupported model family")
    if _digest(artifact) != digest:
        raise ValueError("artifact content digest mismatch")
    return artifact
