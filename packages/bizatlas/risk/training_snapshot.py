"""Immutable training snapshot with explicit feature, label and split provenance.

A snapshot identifies the data used for training; it does not attest that
labels are independently verified or authorize probability publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Sequence

from bizatlas.risk.logistic_model import TrainingRow


@dataclass(frozen=True)
class TrainingSnapshot:
    snapshot_id: str
    observation_cutoff: datetime
    feature_names: tuple[str, ...]
    label_definition: str
    rows: tuple[TrainingRow, ...]
    source_evidence_ids: tuple[str, ...]
    training_group_ids: tuple[str, ...]
    n_positive: int

    def to_document(self) -> dict:
        return {
            "observation_cutoff": self.observation_cutoff.astimezone(timezone.utc).isoformat(),
            "feature_names": list(self.feature_names),
            "label_definition": self.label_definition,
            "rows": [
                {
                    "entity_id": row.entity_id,
                    "group_id": row.group_id,
                    "features": {name: float(row.features[name]) for name in self.feature_names},
                    "label": row.label,
                }
                for row in self.rows
            ],
            "source_evidence_ids": list(self.source_evidence_ids),
            "training_group_ids": list(self.training_group_ids),
            "n_positive": self.n_positive,
        }


def create_training_snapshot(
    rows: Sequence[TrainingRow],
    *,
    feature_names: tuple[str, ...],
    label_definition: str,
    observation_cutoff: datetime,
    source_evidence_ids: Sequence[str],
) -> TrainingSnapshot:
    if observation_cutoff.tzinfo is None or observation_cutoff.utcoffset() is None:
        raise ValueError("observation cutoff must be timezone aware")
    if not label_definition.strip() or not feature_names or len(set(feature_names)) != len(feature_names):
        raise ValueError("invalid label or feature schema")
    if not rows or len({row.entity_id for row in rows}) != len(rows):
        raise ValueError("empty or duplicate entity rows")
    if any(not row.entity_id or not row.group_id or row.label not in (0, 1) for row in rows):
        raise ValueError("invalid entity, group or label")
    if any(set(row.features) != set(feature_names) for row in rows):
        raise ValueError("training feature schema mismatch")
    if any(not math.isfinite(float(value)) for row in rows for value in row.features.values()):
        raise ValueError("nonfinite training feature")
    if not source_evidence_ids or len(set(source_evidence_ids)) != len(source_evidence_ids):
        raise ValueError("nonempty unique evidence references required")
    ordered_rows = tuple(sorted(
        (TrainingRow(row.entity_id, row.group_id,
                     {name: float(row.features[name]) for name in feature_names},
                     row.label) for row in rows),
        key=lambda row: row.entity_id,
    ))
    groups = tuple(sorted({row.group_id for row in ordered_rows}))
    preliminary = TrainingSnapshot(
        "", observation_cutoff, feature_names, label_definition,
        ordered_rows, tuple(sorted(source_evidence_ids)), groups,
        sum(row.label for row in ordered_rows),
    )
    payload = json.dumps(preliminary.to_document(), sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = sha256(payload).hexdigest()
    return TrainingSnapshot(
        digest, observation_cutoff, feature_names, label_definition,
        ordered_rows, tuple(sorted(source_evidence_ids)), groups,
        preliminary.n_positive,
    )
