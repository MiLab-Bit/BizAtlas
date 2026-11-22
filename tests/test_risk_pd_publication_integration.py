"""Synthetic end-to-end scoring contract; no real-world default validation."""
from bizatlas.contracts.models import RiskGrade, RiskResult
from bizatlas.risk.score import enrich_risk


def test_scoring_does_not_expose_unvalidated_probability():
    risk = RiskResult(
        company_id="synthetic-001",
        grade=RiskGrade.YELLOW,
        score=25.0,
        headline="synthetic case",
    )
    distress = {
        "available": True,
        "pd": 0.77,
        "models": {"ohlson": {"pd": 0.66, "partial": True}},
    }
    result = enrich_risk(
        risk, [], distress=distress,
        behavioral={"available": False, "completeness": 0.0},
    )
    output = result.model_dump(mode="json")
    assert output["pd"] is None
    assert output["master_scale"] is None
    assert output["modules"]["calibration"]["pd"] is None
    assert output["modules"]["calibration"]["expected_loss"] is None
    assert output["modules"]["calibration"]["pd_status"] == "PRIOR_ONLY"
    assert not output["modules"]["calibration"]["can_publish_as_empirical_pd"]
    assert "pd" not in output["modules"]["distress"]
    assert "pd" not in output["modules"]["distress"]["models"]["ohlson"]
    assert "0.77" not in str(output["modules"]["distress"])
    assert "0.66" not in str(output["modules"]["distress"])
    # Input remains unchanged; the public representation is a defensive copy.
    assert distress["pd"] == 0.77
    assert distress["models"]["ohlson"]["pd"] == 0.66


def test_no_distress_signal_keeps_probability_unpublished():
    risk = RiskResult(
        company_id="synthetic-002",
        grade=RiskGrade.UNRATED,
        score=0.0,
        headline="insufficient evidence",
    )
    result = enrich_risk(
        risk, [],
        distress={"available": False, "pd": None, "models": {}},
        behavioral={"available": False, "completeness": 0.0},
    )
    assert result.pd is None
    assert result.master_scale is None
    assert result.grade == RiskGrade.UNRATED
