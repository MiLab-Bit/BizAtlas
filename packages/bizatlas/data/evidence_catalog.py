"""Server-managed immutable temporal evidence catalog.

The catalog only stores an upstream admission decision; it does not establish
legal license rights independently. Client requests can reference IDs but
cannot supply replacement temporal or authorization claims.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from bizatlas.data.temporal_evidence import LicenseStatus, TemporalEvidence


def _encode(evidence: TemporalEvidence) -> bytes:
    payload = {
        "evidence_id": evidence.evidence_id,
        "source_id": evidence.source_id,
        "source_sha256": evidence.source_sha256,
        "occurred_at": evidence.occurred_at.isoformat() if evidence.occurred_at else None,
        "effective_from": evidence.effective_from.isoformat() if evidence.effective_from else None,
        "effective_until": evidence.effective_until.isoformat() if evidence.effective_until else None,
        "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
        "ingested_at": evidence.ingested_at.isoformat() if evidence.ingested_at else None,
        "license_status": evidence.license_status.value,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _key(evidence_id: str) -> str:
    if not evidence_id or len(evidence_id) > 256:
        raise ValueError("invalid evidence id")
    return sha256(evidence_id.encode("utf-8")).hexdigest()


def register_evidence(root: Path, evidence: TemporalEvidence) -> Path:
    """Server-only append operation; upstream must validate source grants."""
    blob = _encode(evidence)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (_key(evidence.evidence_id) + ".json")
    if target.exists():
        if target.read_bytes() != blob:
            raise ValueError("immutable evidence id conflict")
        return target
    with NamedTemporaryFile(mode="wb", dir=root, prefix=".evidence-", delete=False) as tmp:
        tmp.write(blob)
        name = tmp.name
    try:
        try:
            os.link(name, target)
        except FileExistsError:
            if target.read_bytes() != blob:
                raise ValueError("concurrent evidence conflict")
    finally:
        os.unlink(name)
    return target


def read_evidence(root: Path, evidence_id: str) -> TemporalEvidence:
    payload = json.loads((root / (_key(evidence_id) + ".json")).read_text(encoding="utf-8"))
    if payload["evidence_id"] != evidence_id:
        raise ValueError("evidence identity mismatch")
    return TemporalEvidence(
        evidence_id=payload["evidence_id"],
        source_id=payload["source_id"],
        source_sha256=payload["source_sha256"],
        occurred_at=datetime.fromisoformat(payload["occurred_at"]) if payload["occurred_at"] else None,
        effective_from=datetime.fromisoformat(payload["effective_from"]) if payload["effective_from"] else None,
        effective_until=datetime.fromisoformat(payload["effective_until"]) if payload["effective_until"] else None,
        published_at=datetime.fromisoformat(payload["published_at"]) if payload["published_at"] else None,
        ingested_at=datetime.fromisoformat(payload["ingested_at"]) if payload["ingested_at"] else None,
        license_status=LicenseStatus(payload["license_status"]),
    )
