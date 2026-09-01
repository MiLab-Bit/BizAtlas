"""Phase C bootstrap 冒烟。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.data.db import init_db
from bizatlas.bootstrap import check_compliance_reconciliation, run_startup_bootstrap


def test_bootstrap_runs():
    init_db()
    result = run_startup_bootstrap()
    assert "llm_seed" in result
    assert "compliance" in result
    assert "seeded" in result["llm_seed"]
    assert "checked" in result["compliance"] or "reason" in result["compliance"]


def test_compliance_check_shape():
    init_db()
    data = check_compliance_reconciliation()
    assert "running_not_declared" in data
    assert "declared_not_running" in data
