"""P0/P1/P2 产品路线新增能力单测与端点冒烟。

覆盖：校准层（已单列）、担保链传染端点、审计/合规端点、数据源优雅降级、
效果反馈落库、MCP JSON-RPC 骨架、可解释溯源索引。
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient


# ---------- 数据源优雅降级（P0-③） ----------
from bizatlas.data.providers_credit_bureau import fetch_credit_report
from bizatlas.data.providers_invoice import extract_invoice


def test_credit_bureau_empty_name():
    r = fetch_credit_report("")
    assert r["ok"] is False and "企业名" in r["message"]


def test_credit_bureau_graceful_when_unconfigured():
    r = fetch_credit_report("某科技有限公司")
    assert r["ok"] is False
    assert "未配置" in r["message"] or "降级" in r["message"]


def test_invoice_ocr_graceful_when_disabled():
    r = extract_invoice("/tmp/fake.png")
    assert r["ok"] is False and "降级" in r["message"]


# ---------- 可解释溯源索引（P1） ----------
from bizatlas.risk.citations import consolidate_citations, render_citations_markdown


def test_consolidate_citations():
    res = {
        "risk": {"hits": [{"rule_id": "R1011", "name": "连续亏损", "dimension": "财务", "severity": "高"}]},
        "citations": [
            {"id": "src1", "label": "商誉占比", "page": 3, "tier": "L1", "value": 0.3}
        ],
    }
    c = consolidate_citations(res)
    assert c["metrics"] and c["rules"]
    md = render_citations_markdown(c)
    assert "溯源" in md and "商誉占比" in md


# ---------- 效果反馈落库（P2） ----------
@pytest.fixture
def feedback_svc(monkeypatch, tmp_path):
    import bizatlas.analytics.feedback as fb

    p = tmp_path / "fb.sqlite"
    conn = sqlite3.connect(str(p))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS feedback_events ("
        "id TEXT PRIMARY KEY, report_id TEXT, company_id TEXT, analyst TEXT, "
        "action TEXT NOT NULL, decision TEXT, comment TEXT, latency_ms REAL, "
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    def gc(db_path=None):
        c = sqlite3.connect(str(p))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(fb, "get_connection", gc)
    return fb


def test_feedback_record_and_summary(feedback_svc):
    rec = feedback_svc.record_feedback(company_id="risky", action="report_accepted")
    assert rec["id"]
    feedback_svc.record_feedback(company_id="risky", action="report_overridden")
    s = feedback_svc.feedback_summary()
    assert s["total_events"] == 2
    assert s["adoption_rate"] == 0.5


def test_feedback_invalid_action(feedback_svc):
    import pytest as _pytest

    with _pytest.raises(ValueError):
        feedback_svc.record_feedback(action="not_a_real_action")


# ---------- MCP 骨架（P2） ----------
from bizatlas.mcp import server as mcp


def test_mcp_initialize():
    r = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r["result"]["serverInfo"]["name"] == "bizatlas"


def test_mcp_tools_list():
    r = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    assert "bizatlas_analyze" in names


def test_mcp_call_analyze():
    r = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "bizatlas_analyze", "arguments": {"company_id": "risky"}},
        }
    )
    assert r.get("result") and r["result"]["content"]


# ---------- 端点冒烟（P0-② 审计 / P1 传染 / P2 度量 / P0-① 校准） ----------
from apps.api.app.main import app


def test_endpoints_smoke():
    with TestClient(app) as c:
        r = c.get("/v1/companies/risky/contagion")
        assert r.status_code == 200
        assert "contagion_score" in r.json()["data"]

        r = c.get("/v1/metrics")
        assert r.status_code == 200 and "http_requests_total" in r.text

        r = c.post("/v1/analytics/feedback", json={"action": "report_accepted", "company_id": "risky"})
        assert r.status_code == 200

        r = c.post("/v1/credit/decision", json={"company_id": "risky"})
        assert r.status_code == 200
        body = r.json()["data"]
        assert "calibration" in body["decision"]
        assert "pd" in body["decision"]["calibration"]
