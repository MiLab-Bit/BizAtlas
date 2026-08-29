from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data.db import init_db
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.rules.engine import load_rules


def setup_module():
    init_db()


def test_seed_rules_count():
    assert len(load_rules()) >= 20


def test_healthy_not_black():
    init_db()
    result = run_analyze(AnalyzeRequest(company_id="healthy", options={"skip_polish": True}))
    assert result["summary"]["grade"] in {"GREEN", "YELLOW"}


def test_risky_elevated():
    init_db()
    result = run_analyze(AnalyzeRequest(company_id="risky", options={"skip_polish": True}))
    assert result["summary"]["grade"] in {"ORANGE", "RED", "BLACK"}
    assert result["rules_hit"] >= 3


def test_defaulted_black_veto():
    init_db()
    result = run_analyze(AnalyzeRequest(company_id="defaulted", options={"skip_polish": True}))
    assert result["summary"]["grade"] == "BLACK"
    assert result["risk"]["veto"]["triggered"] is True
