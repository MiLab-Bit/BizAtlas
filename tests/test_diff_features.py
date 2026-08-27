from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest, DataTier, MetricSource, MetricValue
from bizatlas.data.db import init_db
from bizatlas.industry.benchmarks import compare_to_industry
from bizatlas.orchestrator.analyze import generate_onepager_report, run_analyze
from bizatlas.risk.attribution import build_attribution
from bizatlas.risk.conflicts import detect_conflicts
from bizatlas.risk.score import score_risk
from bizatlas.risk.stress import run_stress
from bizatlas.rules.engine import RuleEngine


def test_conflicts_detect_multi_source():
    obs = [
        MetricValue(
            name="资产负债率",
            value=0.78,
            tier=DataTier.L2,
            source=MetricSource(type="cache", ref="fixture:risky"),
        ),
        MetricValue(
            name="资产负债率",
            value=0.71,
            tier=DataTier.L1,
            source=MetricSource(type="api", ref="akshare:demo"),
        ),
    ]
    conflicts = detect_conflicts(obs)
    assert len(conflicts) >= 1
    assert conflicts[0]["metric"] == "资产负债率"


def test_stress_raises_or_holds():
    init_db()
    result = run_analyze(AnalyzeRequest(company_id="risky", options={"include_stress": True}))
    stress = result["stress"]
    assert stress and stress["scenarios"]
    assert stress["worst"]
    assert len(stress["scenarios"]) >= 3


def test_attribution_five_dims():
    engine = RuleEngine()
    from bizatlas.ingest.fixtures import load_fixture_company

    data = load_fixture_company("risky")
    metrics = data["_metrics"]
    hits = engine.match(metrics, events=data["_events"])
    risk = score_risk("risky", metrics, hits, events=data["_events"])
    attr = build_attribution(risk.dimensions, hits, metrics)
    assert len(attr) == 5
    assert any(a["hit_count"] > 0 for a in attr)


def test_industry_benchmark_risky():
    from bizatlas.ingest.fixtures import load_fixture_company

    data = load_fixture_company("risky")
    bench = compare_to_industry(data.get("industry"), data["_metrics"])
    assert bench["rows"]
    assert bench["warn_count"] >= 1


def test_analyze_includes_diff_blocks():
    init_db()
    result = run_analyze(AnalyzeRequest(company_id="risky"))
    assert result["conflicts"]
    assert result["attribution"]
    assert result["industry_benchmark"]["rows"]
    assert result["stress"]["scenarios"]
    assert result["graph"]["nodes"]


def test_pdf_export():
    init_db()
    out = generate_onepager_report("risky", confirm_export=True)
    assert out["pdf_path"]
    assert Path(out["pdf_path"]).exists()


def test_run_stress_direct():
    from bizatlas.ingest.fixtures import load_fixture_company

    data = load_fixture_company("healthy")
    out = run_stress("healthy", data["_metrics"], data["_events"])
    assert out["baseline"]["score"] >= 0
    assert out["scenarios"]
