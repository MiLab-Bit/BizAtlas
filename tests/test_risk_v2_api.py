"""B-RCF v2.0.1 风控体系端点测试：GET /v1/risk/{company_id}。

验证融合层对外暴露的综合分 / 主标尺 / PD / reason codes 结构，
以及「困境层数据缺口不得稀释规则分」在 API 层的可见性（layer_severity）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from apps.api.app.main import app

    return TestClient(app)


def _risk_payload(client, company_id: str) -> dict:
    r = client.get(f"/v1/risk/{company_id}", params={"fast": True})
    assert r.status_code == 200, r.text
    env = r.json()
    assert env["ok"] is True, env.get("error")
    return env["data"]["risk"]


def test_risk_endpoint_returns_v2_payload(client):
    risk = _risk_payload(client, "risky")

    # 综合分与评级：重度困境主体不得被融合层稀释
    assert risk["score"] == 96.2
    assert risk["grade"] == "BLACK"

    # v2 结构：主标尺 / PD / 融合审计
    assert risk["master_scale"] in {"A", "BBB", "BB", "B", "CCC", "CC", "C", "D"}
    assert 0.0 < risk["pd"] < 1.0

    mods = risk["modules"]
    assert mods["version"] == "2.0.1"
    assert mods["fusion_mode"] == "rule_baseline_uplift"
    # 困境层数据缺口 → 不参与融合（v2.0.1 修复回归）
    assert mods["layer_severity"]["distress"] is None
    assert mods["blend_weights"]["distress"] == 0.0
    assert mods["uplift_total"] == 0.0
    assert isinstance(mods["reason_codes"], list) and mods["reason_codes"]


def test_risk_endpoint_healthy_is_green(client):
    risk = _risk_payload(client, "healthy")
    assert risk["grade"] == "GREEN"
    assert risk["score"] == 0.0
    assert risk["modules"]["version"] == "2.0.1"


def test_risk_endpoint_unknown_company_is_not_fake_ok(client):
    """未知主体不得返回 ok=True 的伪造结论。"""
    r = client.get("/v1/risk/nope-co", params={"fast": True})
    assert r.status_code != 200 or r.json()["ok"] is False
