from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.data.db import init_db
from bizatlas.workflow.due_diligence import advance_due_diligence, start_due_diligence


def main() -> None:
    init_db()
    wf = start_due_diligence(fixture_id="defaulted")
    print("start", wf["id"], wf["stage"], wf["required_ready"])
    wf = advance_due_diligence(wf["id"], action="analyze")
    print("analyze", wf["stage"], wf["analyze"]["summary"])
    wf = advance_due_diligence(wf["id"], action="report")
    print("report", wf["stage"], wf["report"]["report_id"])
    wf = advance_due_diligence(wf["id"], action="submit", confirm=True)
    print("submit", wf["stage"], wf["report"].get("export_path"))
    print("smoke_workflow_ok")


if __name__ == "__main__":
    main()
