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
    # risky 为高风险等级，报告后进入"需复核"状态
    assert reported["requires_review"] is True

    try:
        advance_due_diligence(wf["id"], action="submit", confirm=False)
        assert False, "should require confirm"
    except ValueError as exc:
        assert "confirm" in str(exc)

    # 高风险结论：提交前必须通过人工复核（人在回路硬门禁）
    try:
        advance_due_diligence(wf["id"], action="submit", confirm=True)
        assert False, "高风险未复核不应允许提交"
    except ValueError as exc:
        assert "复核" in str(exc)

    from bizatlas.workflow.due_diligence import review_due_diligence

    reviewed = review_due_diligence(
        wf["id"], reviewer="风控总监", decision="approve", comment="同意"
    )
    assert reviewed["review_passed"] is True

    submitted = advance_due_diligence(wf["id"], action="submit", confirm=True)
    assert submitted["stage"] == "submitted"
    assert submitted["report"].get("export_path")
