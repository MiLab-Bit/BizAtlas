"""Credit-event ontology and observation-window labeling.

ST/*ST is a regulatory distress proxy, not a contractual default. Guarantee
obligation and actual payout are separate events. Unknown history never
becomes a negative label.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class CreditEventType(str, Enum):
    FIRST_ST = "FIRST_ST"
    ST_REMOVAL = "ST_REMOVAL"
    ST_REENTRY = "ST_REENTRY"
    CONTRACT_DEFAULT = "CONTRACT_DEFAULT"
    GUARANTEE_OBLIGATION = "GUARANTEE_OBLIGATION"
    GUARANTEE_PAYOUT = "GUARANTEE_PAYOUT"


class LabelStatus(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE_OBSERVED = "NEGATIVE_OBSERVED"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CreditEvent:
    company_id: str
    kind: CreditEventType
    effective_date: date
    announced_date: date | None
    evidence_id: str
    independently_verified: bool = False


@dataclass(frozen=True)
class EventLabel:
    status: LabelStatus
    event_type: CreditEventType
    observation_date: date
    horizon_end: date
    event_date: date | None
    evidence_id: str | None
    reason: str


def label_credit_event(
    *,
    event_type: CreditEventType,
    observation_date: date,
    horizon_end: date,
    coverage_end: date | None,
    events: list[CreditEvent],
    complete_event_history: bool,
    require_independent_verification: bool = True,
) -> EventLabel:
    """Construct a label only from events published by the horizon.

    This routine is for retrospective label construction, not model features.
    It does not allow future announcements into as-of features. A label is
    negative only with explicit complete history and full horizon coverage.
    """
    if horizon_end <= observation_date:
        raise ValueError("horizon_end must be later than observation_date")
    if coverage_end is None:
        return EventLabel(LabelStatus.UNKNOWN, event_type, observation_date, horizon_end,
                          None, None, "coverage_end_missing")
    candidates = sorted(
        (
            e for e in events
            if e.kind is event_type
            and observation_date < e.effective_date <= horizon_end
            and e.announced_date is not None
            and e.announced_date <= coverage_end
            and (not require_independent_verification or e.independently_verified)
        ),
        key=lambda e: (e.effective_date, e.evidence_id),
    )
    if candidates:
        first = candidates[0]
        return EventLabel(LabelStatus.POSITIVE, event_type, observation_date, horizon_end,
                          first.effective_date, first.evidence_id, "verified_event")
    if coverage_end < horizon_end:
        return EventLabel(LabelStatus.RIGHT_CENSORED, event_type, observation_date,
                          horizon_end, None, None, "followup_incomplete")
    if not complete_event_history:
        return EventLabel(LabelStatus.UNKNOWN, event_type, observation_date,
                          horizon_end, None, None, "event_history_unverified")
    return EventLabel(LabelStatus.NEGATIVE_OBSERVED, event_type, observation_date,
                      horizon_end, None, None, "complete_followup_no_event")
