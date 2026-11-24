"""Provider-independent data-source admission; no network calls or credentials.

A configured API key is not a license grant. An ingestion timestamp is not
evidence of historical availability. The source must supply both.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
import json

from bizatlas.data.temporal_evidence import LicenseStatus, TemporalEvidence, _utc


@dataclass(frozen=True)
class SourceGrant:
    source_id: str
    license_status: LicenseStatus
    allowed_purposes: frozenset[str]
    valid_until: datetime | None
    grant_reference: str | None

    def permits(self, purpose: str, at: datetime) -> bool:
        return (
            self.license_status is LicenseStatus.AUTHORIZED
            and bool(self.grant_reference)
            and purpose in self.allowed_purposes
            and (self.valid_until is None or _utc(at) < _utc(self.valid_until))
        )


@dataclass(frozen=True)
class SourceRecord:
    evidence: TemporalEvidence
    payload: dict[str, Any]


def admit_provider_record(
    *,
    source_id: str,
    evidence_id: str,
    payload: dict[str, Any],
    published_at: datetime | None,
    ingested_at: datetime,
    grant: SourceGrant,
    purpose: str = "historical_risk_research",
    occurred_at: datetime | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
) -> SourceRecord:
    """Build immutable provenance from an explicitly granted provider record.

    Grant failures fail closed. The caller must still run as-of admission:
    successful ingestion does not establish historical eligibility.
    """
    if source_id != grant.source_id:
        raise ValueError("source grant does not match provider")
    if not grant.permits(purpose, ingested_at):
        raise PermissionError("source use is not authorized for requested purpose")
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    evidence = TemporalEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        source_sha256=digest,
        occurred_at=occurred_at,
        effective_from=effective_from,
        effective_until=effective_until,
        published_at=published_at,
        ingested_at=ingested_at,
        license_status=grant.license_status,
    )
    return SourceRecord(evidence, dict(payload))
