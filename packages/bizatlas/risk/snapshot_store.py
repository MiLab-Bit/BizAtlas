"""Immutable JSON storage for provenance-aware training snapshots.

The canonical snapshot hash is recomputed after loading. No pickle, dynamic
code execution or mutable overwrite is supported.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from bizatlas.risk.logistic_model import TrainingRow
from bizatlas.risk.training_snapshot import TrainingSnapshot, create_training_snapshot


def _snapshot_bytes(snapshot: TrainingSnapshot) -> bytes:
    payload = json.dumps(
        snapshot.to_document(), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")
    if sha256(payload).hexdigest() != snapshot.snapshot_id:
        raise ValueError("snapshot digest mismatch")
    return payload


def save_training_snapshot(root: Path, snapshot: TrainingSnapshot) -> Path:
    payload = _snapshot_bytes(snapshot)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (snapshot.snapshot_id + ".json")
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError("existing snapshot content mismatch")
        return target
    with NamedTemporaryFile(mode="wb", dir=root, prefix=".snapshot-", delete=False) as tmp:
        tmp.write(payload)
        temp_name = tmp.name
    try:
        try:
            os.link(temp_name, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError("concurrent snapshot content mismatch")
    finally:
        os.unlink(temp_name)
    return target


def load_training_snapshot(root: Path, snapshot_id: str) -> TrainingSnapshot:
    if len(snapshot_id) != 64 or any(c not in "0123456789abcdef" for c in snapshot_id):
        raise ValueError("invalid snapshot id")
    blob = (root / (snapshot_id + ".json")).read_bytes()
    if sha256(blob).hexdigest() != snapshot_id:
        raise ValueError("snapshot bytes digest mismatch")
    payload = json.loads(blob)
    rows = [
        TrainingRow(
            entity_id=item["entity_id"],
            group_id=item["group_id"],
            features=item["features"],
            label=item["label"],
        )
        for item in payload["rows"]
    ]
    snapshot = create_training_snapshot(
        rows,
        feature_names=tuple(payload["feature_names"]),
        label_definition=payload["label_definition"],
        observation_cutoff=datetime.fromisoformat(payload["observation_cutoff"]),
        source_evidence_ids=payload["source_evidence_ids"],
    )
    if snapshot.snapshot_id != snapshot_id:
        raise ValueError("snapshot reconstruction digest mismatch")
    if list(snapshot.training_group_ids) != payload["training_group_ids"]:
        raise ValueError("snapshot training groups mismatch")
    if snapshot.n_positive != payload["n_positive"]:
        raise ValueError("snapshot label count mismatch")
    return snapshot
