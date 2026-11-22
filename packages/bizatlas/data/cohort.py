"""Leakage-aware offline cohort construction.

No synthetic observation is interpreted as real default evidence. A row is
eligible only when its identity, features and observation horizon are audited.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from bizatlas.data.credit_events import CreditEvent, CreditEventType, EventLabel, label_credit_event
from bizatlas.data.temporal_evidence import (
    EvidenceDecision,
    TemporalEvidence,
    eligible_as_of,
)


@dataclass(frozen=True)
class CohortCandidate:
    entity_id: str
    group_id: str
    observation_at: datetime
    horizon_end: date
    coverage_end: date | None
    complete_event_history: bool
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class CohortRow:
    entity_id: str
    group_id: str
    observation_at: datetime
    evidence_ids: tuple[str, ...]
    label: EventLabel


@dataclass(frozen=True)
class CohortExclusion:
    entity_id: str
    reason: str


def build_cohort(
    candidates: list[CohortCandidate],
    evidence: list[TemporalEvidence],
    events_by_entity: dict[str, list[CreditEvent]],
    label_type: CreditEventType,
) -> tuple[list[CohortRow], list[CohortExclusion]]:
    """Require every selected feature to pass the as-of admission gate."""
    by_id = {e.evidence_id: e for e in evidence}
    if len(by_id) != len(evidence):
        raise ValueError("duplicate evidence ids")
    rows: list[CohortRow] = []
    excluded: list[CohortExclusion] = []
    for c in candidates:
        if not c.entity_id or not c.group_id:
            excluded.append(CohortExclusion(c.entity_id, "missing_entity_or_group"))
            continue
        if not c.evidence_ids:
            excluded.append(CohortExclusion(c.entity_id, "no_feature_evidence"))
            continue
        if len(set(c.evidence_ids)) != len(c.evidence_ids):
            excluded.append(CohortExclusion(c.entity_id, "duplicate_feature_evidence"))
            continue
        if any(eid not in by_id for eid in c.evidence_ids):
            excluded.append(CohortExclusion(c.entity_id, "unresolved_feature_evidence"))
            continue
        selected = [by_id[eid] for eid in c.evidence_ids]
        accepted, decisions = eligible_as_of(selected, c.observation_at)
        if len(accepted) != len(selected):
            reasons = sorted({
                decision.value for decision in decisions.values()
                if decision is not EvidenceDecision.ADMISSIBLE
            })
            excluded.append(CohortExclusion(c.entity_id, "inadmissible_features:" + ",".join(reasons)))
            continue
        label = label_credit_event(
            event_type=label_type,
            observation_date=c.observation_at.date(),
            horizon_end=c.horizon_end,
            coverage_end=c.coverage_end,
            events=events_by_entity.get(c.entity_id, []),
            complete_event_history=c.complete_event_history,
        )
        rows.append(CohortRow(
            c.entity_id, c.group_id, c.observation_at, c.evidence_ids, label
        ))
    return rows, excluded


def group_disjoint_split(
    rows: list[CohortRow],
    cutoff: datetime,
    *,
    embargo_days: int = 30,
) -> tuple[list[CohortRow], list[CohortRow], list[CohortExclusion]]:
    """Conservative group-disjoint temporal split.

    Train labels must mature before the embargo begins. Groups occurring on
    both sides are excluded from holdout rather than silently leaking.
    """
    from datetime import timedelta

    if embargo_days < 0:
        raise ValueError("embargo_days must be nonnegative")
    boundary = cutoff.date() - timedelta(days=embargo_days)
    training = [
        row for row in rows
        if row.observation_at < cutoff
        and row.label.horizon_end < boundary
        and row.label.status.value in ("POSITIVE", "NEGATIVE_OBSERVED")
    ]
    train_groups = {row.group_id for row in training}
    holdout = [
        row for row in rows
        if row.observation_at >= cutoff and row.group_id not in train_groups
    ]
    excluded = [
        CohortExclusion(row.entity_id, "embargo_or_group_overlap")
        for row in rows if row not in training and row not in holdout
    ]
    return training, holdout, excluded
