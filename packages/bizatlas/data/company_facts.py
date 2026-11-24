from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from bizatlas.data.source_admission import SourceRecord
from bizatlas.data.evidence_catalog import register_evidence, read_evidence
from bizatlas.data.temporal_evidence import TemporalEvidence
from bizatlas.risk.feature_bridge import FeatureObservation


def _key(evidence_id: str) -> str:
    return sha256(evidence_id.encode()).hexdigest()


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def register_company_fact(root: Path, record: SourceRecord) -> Path:
    payload = record.payload
    if sha256(_canonical(payload)).hexdigest() != record.evidence.source_sha256:
        raise ValueError("source payload digest mismatch")
    for key in ("company_id", "name", "unit"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("invalid company fact identity or schema")
    value = payload.get("value")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)):
        raise ValueError("invalid fact value")
    register_evidence(root / "evidence", record.evidence)
    directory = root / "facts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (_key(record.evidence.evidence_id) + ".json")
    blob = _canonical(payload)
    with NamedTemporaryFile(dir=directory, delete=False) as tmp:
        tmp.write(blob)
        name = tmp.name
    try:
        try:
            os.link(name, target)
        except FileExistsError:
            if target.read_bytes() != blob:
                raise ValueError("immutable fact conflict")
    finally:
        os.unlink(name)
    return target


def read_company_fact(root: Path, company_id: str, evidence_id: str) -> tuple[FeatureObservation, TemporalEvidence]:
    evidence = read_evidence(root / "evidence", evidence_id)
    blob = (root / "facts" / (_key(evidence_id) + ".json")).read_bytes()
    if sha256(blob).hexdigest() != evidence.source_sha256:
        raise ValueError("fact digest mismatch")
    payload = json.loads(blob)
    if payload["company_id"] != company_id:
        raise ValueError("evidence does not belong to requested company")
    return FeatureObservation(payload["name"], payload["value"], evidence_id, payload["unit"]), evidence
