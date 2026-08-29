from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.data import repo
from bizatlas.data.db import init_db
from bizatlas.ingest.upload import ingest_metrics_file
from bizatlas.orchestrator.analyze import generate_onepager_report, run_analyze
from bizatlas.contracts.models import AnalyzeRequest


def test_upload_csv_analyze_and_report(tmp_path, monkeypatch):
    init_db()
    monkeypatch.setenv("BIZATLAS_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BIZATLAS_EXPORT_DIR", str(tmp_path / "exports"))
    # refresh settings cache
    from bizatlas.config import get_settings

    get_settings.cache_clear()

    company = repo.create_company("单测上传企业", "制造")
    csv_path = ROOT / "content" / "templates" / "metrics_template.csv"
    content = csv_path.read_bytes()
    ingested = ingest_metrics_file(company["id"], "metrics_template.csv", content)
    assert ingested["metrics_count"] >= 10

    analyzed = run_analyze(AnalyzeRequest(company_id=company["id"], intent="analyze_risk"))
    assert analyzed["metrics_count"] >= 10
    assert analyzed["summary"]["grade"] in {"ORANGE", "RED", "BLACK", "YELLOW"}

    report = generate_onepager_report(company["id"], confirm_export=True)
    assert report["report_id"]
    assert "一页风险摘要" in report["markdown"]
    assert report["export_path"]
    assert Path(report["export_path"]).exists()

    get_settings.cache_clear()
