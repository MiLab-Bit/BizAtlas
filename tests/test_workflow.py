from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.data.db import init_db
from bizatlas.workflow.due_diligence import advance_due_diligence, start_due_diligence


def test_due_diligence_fixture_flow():
    init_db()
    wf = start_due_diligence(fixture_id="risky")
    assert wf["required_ready"] is True
    assert wf["stage"] in {"ready", "checklist"}

    analyzed = advance_due_diligence(wf["id"], action="analyze")
    assert analyzed["stage"] == "analyzed"
    assert analyzed["analyze"]["summary"]["grade"] in {"ORANGE", "RED", "BLACK"}

    reported = advance_due_diligence(wf["id"], action="report")
    assert reported["stage"] == "awaiting_human"
    assert reported["report"]["report_id"]

    try:
        advance_due_diligence(wf["id"], action="submit", confirm=False)
        assert False, "should require confirm"
    except ValueError as exc:
        assert "confirm" in str(exc)

    submitted = advance_due_diligence(wf["id"], action="submit", confirm=True)
    assert submitted["stage"] == "submitted"
    assert submitted["report"].get("export_path")
