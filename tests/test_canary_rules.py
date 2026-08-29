"""规则灰度（canary）与热更新（reload 端点）测试。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import MetricValue
from bizatlas.rules.engine import RuleEngine, _canary_pass


def _rule(rid: str, canary=None) -> dict:
    r = {
        "id": rid,
        "name": rid,
        "dimension": "财务",
        "severity": "中",
        "condition": {"type": "threshold", "metric": "x", "op": ">", "value": 0},
        "contribute_to_score": True,
    }
    if canary is not None:
        r["canary"] = canary
    return r


def _metrics() -> dict:
    return {"x": MetricValue(name="x", value=10)}


def test_canary_default_full():
    eng = RuleEngine([_rule("r1")])
    assert len(eng.match(_metrics(), canary_key="companyA")) == 1


def test_canary_zero_skips_all():
    eng = RuleEngine([_rule("r1", canary=0.0)])
    assert len(eng.match(_metrics(), canary_key="companyA")) == 0


def test_canary_one_full():
    eng = RuleEngine([_rule("r1", canary=1.0)])
    assert len(eng.match(_metrics(), canary_key="companyA")) == 1


def test_canary_deterministic_per_key():
    eng = RuleEngine([_rule("r1", canary=0.5)])
    a1 = eng.match(_metrics(), canary_key="companyA")
    a2 = eng.match(_metrics(), canary_key="companyA")
    assert (len(a1) == 1) == (len(a2) == 1)
    b1 = eng.match(_metrics(), canary_key="companyB")
    b2 = eng.match(_metrics(), canary_key="companyB")
    assert (len(b1) == 1) == (len(b2) == 1)


def test_canary_pass_unit():
    assert _canary_pass({"id": "r"}, None) is True
    assert _canary_pass({"id": "r"}, "x") is True
    assert _canary_pass({"id": "r", "canary": 1.0}, "x") is True
    assert _canary_pass({"id": "r", "canary": 0.0}, "x") is False


def test_reload_endpoint():
    sys.path.insert(0, str(ROOT / "apps"))
    try:
        from fastapi.testclient import TestClient
        from apps.api.app.main import app
    except Exception as e:  # noqa: BLE001
        import pytest

        pytest.skip(f"apps not importable in this env: {e}")
    client = TestClient(app)
    resp = client.post("/v1/rules/reload")
    assert resp.status_code == 200
    assert resp.json()["data"]["reloaded"] >= 0
