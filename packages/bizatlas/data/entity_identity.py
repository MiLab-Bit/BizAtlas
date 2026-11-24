"""Point-in-time corporate identity resolution without fuzzy silent merges.

Aliases and ticker symbols are not permanent legal identifiers. Historical
names must be backed by evidence and a known publication timestamp.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bizatlas.data.temporal_evidence import _utc


@dataclass(frozen=True)
class IdentityAlias:
    entity_id: str
    alias: str
    effective_from: datetime
    effective_until: datetime | None
    published_at: datetime
    evidence_id: str
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.entity_id.strip() or not self.alias.strip() or not self.evidence_id.strip():
            raise ValueError("entity, alias and evidence reference required")
        if self.effective_until is not None and (
            _utc(self.effective_until) <= _utc(self.effective_from)
        ):
            raise ValueError("invalid alias effective interval")
        _utc(self.published_at)


@dataclass(frozen=True)
class IdentityResolution:
    entity_id: str | None
    reason: str
    evidence_ids: tuple[str, ...] = ()


def resolve_entity_at(
    alias: str,
    as_of: datetime,
    records: list[IdentityAlias],
) -> IdentityResolution:
    """Resolve only uniquely evidenced aliases known at the requested time."""
    cutoff = _utc(as_of)
    normalized = alias.strip().casefold()
    if not normalized:
        return IdentityResolution(None, "empty_alias")
    candidates = [
        record for record in records
        if record.alias.strip().casefold() == normalized
        and record.verified
        and _utc(record.published_at) <= cutoff
        and _utc(record.effective_from) <= cutoff
        and (
            record.effective_until is None
            or cutoff < _utc(record.effective_until)
        )
    ]
    ids = {record.entity_id for record in candidates}
    if not ids:
        return IdentityResolution(None, "no_verified_as_of_match")
    if len(ids) != 1:
        return IdentityResolution(None, "ambiguous_alias")
    return IdentityResolution(
        next(iter(ids)),
        "verified_as_of",
        tuple(sorted({record.evidence_id for record in candidates})),
    )
