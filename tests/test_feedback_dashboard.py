from __future__ import annotations

from bizatlas.analytics import feedback as feedback_svc
from bizatlas.data.db import get_connection


def _cleanup(ids):
    conn = get_connection()
    try:
        for i in ids:
            conn.execute("DELETE FROM feedback_events WHERE id = ?", (i,))
        conn.commit()
    finally:
        conn.close()


def test_feedback_dashboard_aggregates():
    r1 = feedback_svc.record_feedback(company_id="c1", action="decision_accepted", decision="approve", latency_ms=120.0)
    r2 = feedback_svc.record_feedback(company_id="c2", action="decision_overridden", decision="reject", latency_ms=200.0)
    try:
        dash = feedback_svc.feedback_dashboard()
        assert dash["total_events"] >= 2
        assert dash["by_action"].get("decision_accepted") >= 1
        assert dash["by_action"].get("decision_overridden") >= 1
        assert dash["adoption_rate"] is not None
        assert abs(dash["avg_latency_ms"] - 160.0) < 1e-6
        assert any(e["action"] == "decision_accepted" for e in dash["recent"])
    finally:
        _cleanup([r1["id"], r2["id"]])
