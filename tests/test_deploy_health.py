"""阶段 3 部署集成测试：健康探针 / 指标 / RBAC 门禁（FastAPI TestClient）。"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from bizatlas.auth.rbac import Role, issue_token
from bizatlas.config import get_settings


@pytest.fixture
def client():
    from apps.api.app.main import app

    return TestClient(app)


# —— 健康与指标（开发态放行，无 token）——
def test_health_live(client):
    r = client.get("/v1/health/live")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "up"


def test_health_ready(client):
    r = client.get("/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"
    assert r.json()["data"]["db_ok"] is True


def test_metrics_endpoint(client):
    r = client.get("/v1/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text
    # JSON 形态
    rj = client.get("/v1/metrics?fmt=json")
    assert rj.status_code == 200
    assert "counters" in rj.json()


# —— RBAC 门禁（开启鉴权后）——
@pytest.fixture
def auth_client():
    secret = "test-secret-phase3"
    os.environ["BIZATLAS_AUTH_SECRET"] = secret
    os.environ["BIZATLAS_AUTH_DISABLED"] = "false"
    get_settings.cache_clear()
    from apps.api.app.main import app

    c = TestClient(app)
    yield c, secret
    # 还原，避免影响其他用例
    os.environ.pop("BIZATLAS_AUTH_SECRET", None)
    os.environ["BIZATLAS_AUTH_DISABLED"] = "true"
    get_settings.cache_clear()


def _headers(role: Role, secret: str) -> dict:
    return {"Authorization": f"Bearer {issue_token('u', role, secret)}"}


def test_admin_rbac_gate(auth_client):
    c, secret = auth_client
    # 无 token → 401
    assert c.get("/v1/admin/rbac").status_code == 401
    # viewer → 403
    assert c.get("/v1/admin/rbac", headers=_headers(Role.VIEWER, secret)).status_code == 403
    # admin → 200
    r = c.get("/v1/admin/rbac", headers=_headers(Role.ADMIN, secret))
    assert r.status_code == 200
    assert "matrix" in r.json()["data"]


def test_review_gate(auth_client):
    c, secret = auth_client
    # viewer 无复核权 → 403（未到达业务）
    r = c.post(
        "/v1/workflows/nope/review",
        json={"decision": "approve"},
        headers=_headers(Role.VIEWER, secret),
    )
    assert r.status_code == 403
    # admin 通过鉴权，到达业务（workflow 不存在 → 404，证明已越过门禁）
    r = c.post(
        "/v1/workflows/nope/review",
        json={"decision": "approve"},
        headers=_headers(Role.ADMIN, secret),
    )
    assert r.status_code == 404


def test_export_gate(auth_client):
    c, secret = auth_client
    # viewer 无权导出 → 403
    r = c.post(
        "/v1/reports",
        json={"company_id": "x", "confirm": True},
        headers=_headers(Role.VIEWER, secret),
    )
    assert r.status_code == 403
    # admin 通过鉴权，到达业务（company 不存在 → 404）
    r = c.post(
        "/v1/reports",
        json={"company_id": "x", "confirm": True},
        headers=_headers(Role.ADMIN, secret),
    )
    assert r.status_code == 404
