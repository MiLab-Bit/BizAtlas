"""Offline, synthetic contract checks; not empirical calibration evidence."""
from datetime import date

from bizatlas.risk.calibration_contract import (
    ProbabilityEvidence,
    ProbabilityStatus,
    assess_probability_publication,
)


def valid_evidence() -> ProbabilityEvidence:
    return ProbabilityEvidence(
        label_definition="first_contract_default_12m",
        calibration_version="test-fixture-v1",
        observation_end=date(2023, 12, 31),
        holdout_end=date(2025, 12, 31),
        point_in_time_audited=True,
        authorized_data=True,
        independent_holdout_passed=True,
        sufficient_label_followup=True,
    )


def test_no_data_is_unrated_not_safe():
    r = assess_probability_publication(None)
    assert r.status == ProbabilityStatus.UNRATED
    assert r.pd is None
    assert not r.can_publish_as_empirical_pd


def test_expert_prior_cannot_be_published_as_empirical():
    r = assess_probability_publication(0.95)
    assert r.status == ProbabilityStatus.PRIOR_ONLY
    assert not r.can_publish_as_empirical_pd


def test_invalid_probabilities_are_rejected():
    for value in (-0.01, 1.01, float("nan"), float("inf")):
        r = assess_probability_publication(value, valid_evidence())
        assert r.status == ProbabilityStatus.UNRATED
        assert r.pd is None


def test_incomplete_evidence_fails_closed():
    e = ProbabilityEvidence(label_definition="ST_proxy")
    r = assess_probability_publication(0.2, e)
    assert r.status == ProbabilityStatus.PRIOR_ONLY
    assert not r.can_publish_as_empirical_pd


def test_invalid_chronology_blocks_publication():
    e = valid_evidence()
    invalid = ProbabilityEvidence(
        **{**e.__dict__, "holdout_end": date(2022, 12, 31)}
    )
    r = assess_probability_publication(0.2, invalid)
    assert r.reason == "invalid_holdout_chronology"
    assert not r.can_publish_as_empirical_pd


def test_complete_fixture_gate_is_explicitly_conditional():
    # Passing a fixture is not evidence of actual validation; callers must
    # supply truthful, audited metadata from the independent holdout process.
    r = assess_probability_publication(0.2, valid_evidence())
    assert r.status == ProbabilityStatus.VALIDATED
    assert r.can_publish_as_empirical_pd
