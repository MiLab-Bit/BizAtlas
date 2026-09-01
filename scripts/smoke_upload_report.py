"""Smoke: CSV upload → analyze → onepager export."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data import repo
from bizatlas.data.db import init_db
from bizatlas.ingest.upload import ingest_metrics_file
from bizatlas.orchestrator.analyze import generate_onepager_report, run_analyze


def main() -> None:
    init_db()
    company = repo.create_company("烟测上传企业", "制造")
    csv_path = ROOT / "content" / "templates" / "metrics_template.csv"
    ingested = ingest_metrics_file(company["id"], csv_path.name, csv_path.read_bytes())
    print("ingest", ingested["metrics_count"], ingested["document_id"])

    analyzed = run_analyze(AnalyzeRequest(company_id=company["id"]))
    print(
        "analyze",
        analyzed["summary"]["grade"],
        analyzed["summary"]["score"],
        analyzed["rules_hit"],
    )

    report = generate_onepager_report(company["id"], confirm_export=True)
    print("report", report["report_id"], report["export_path"])
    print("smoke_upload_ok")


if __name__ == "__main__":
    main()
