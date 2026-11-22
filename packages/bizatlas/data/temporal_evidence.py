"""Point-in-time evidence contracts for historical credit investigations.

A fact's occurrence time is not its availability time. This module separates
event validity, publication and ingestion to prevent hindsight leakage.
No external provider access is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class LicenseStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    UNVERIFIED = "UNVERIFIED"
    PROHIBITED = "PROHIBITED"


class EvidenceDecision(str, Enum):
    ADMISSIBLE = "ADMISSIBLE"
    FUTURE_INFORMATION = "FUTURE_INFORMATION"
    UNKNOWN_AVAILABILITY = "UNKNOWN_AVAILABILITY"
    UNAUTHORIZED_SOURCE = "UNAUTHORIZED_SOURCE"
    INVALID_TIMELINE = "INVALID_TIMELINE"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include timezone")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TemporalEvidence:
    evidence_id: str
    source_id: str
    source_sha256: str
    occurred_at: datetime | None
    effective_from: datetime | None
    effective_until: datetime | None
    published_at: datetime | None
    ingested_at: datetime | None
    license_status: LicenseStatus = LicenseStatus.UNVERIFIED

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.source_id or len(self.source_sha256) != 64:
            raise ValueError("evidence_id, source_id and 64-character sha256 required")
        for value in (
            self.occurred_at,
            self.effective_from,
            self.effective_until,
            self.published_at,
            self.ingested_at,
        ):
            if value is not None:
                _utc(value)
        if self.effective_from and self.effective_until:
            if _utc(self.effective_until) <= _utc(self.effective_from):
                raise ValueError("effective interval must be nonempty")

    def assess(self, as_of: datetime) -> EvidenceDecision:
        cutoff = _utc(as_of)
        if self.license_status is not LicenseStatus.AUTHORIZED:
            return EvidenceDecision.UNAUTHORIZED_SOURCE
        if self.published_at is None or self.ingested_at is None:
            return EvidenceDecision.UNKNOWN_AVAILABILITY
        published, ingested = _utc(self.published_at), _utc(self.ingested_at)
        if ingested < published:
            return EvidenceDecision.INVALID_TIMELINE
        if published > cutoff or ingested > cutoff:
            return EvidenceDecision.FUTURE_INFORMATION
        if self.effective_from and _utc(self.effective_from) > cutoff:
            return EvidenceDecision.FUTURE_INFORMATION
        if self.effective_until and _utc(self.effective_until) <= cutoff:
            return EvidenceDecision.FUTURE_INFORMATION
        return EvidenceDecision.ADMISSIBLE


def eligible_as_of(
    evidence: list[TemporalEvidence], as_of: datetime
) -> tuple[list[TemporalEvidence], dict[str, EvidenceDecision]]:
    """Return eligible evidence and all exclusions, with no silent negative labels."""
    accepted: list[TemporalEvidence] = []
    decisions: dict[str, EvidenceDecision] = {}
    for item in evidence:
        if item.evidence_id in decisions:
            raise ValueError(f"duplicate evidence_id: {item.evidence_id}")
        decision = item.assess(as_of)
        decisions[item.evidence_id] = decision
        if decision is EvidenceDecision.ADMISSIBLE:
            accepted.append(item)
    return accepted, decisions
