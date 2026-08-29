"""邮箱用户系统（身份基础设施）离线测试。

不触网、确定性；使用临时 SQLite，避免污染业务库。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from bizatlas.config import get_settings
from bizatlas.data.db import init_db
from bizatlas.identity import (
    IdentityError,
    authenticate,
    get_user_by_email,
    hash_password,
    list_audit,
    logout,
    refresh,
    register,
    verify_password,
)


@pytest.fixture
def identity_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "identity.sqlite")
    monkeypatch.setenv("BIZATLAS_DB_PATH", db_path)
    monkeypatch.setenv("BIZATLAS_AUTH_SECRET", "test-secret")
    get_settings.cache_clear()
    init_db(db_path)
    yield db_path
    get_settings.cache_clear()


def test_register_and_lookup(identity_db):
    u = register("alice@example.com", "supersecret", nickname="Alice")
    assert u.email == "alice@example.com"
    assert u.role == "viewer"
    assert u.status == "active"
    assert u.public_id != u.id  # 对外暴露 public_id，不泄露内部 row id
    # 邮箱大小写归一
    assert get_user_by_email("ALICE@EXAMPLE.COM").public_id == u.public_id


def test_register_duplicate(identity_db):
    register("bob@example.com", "supersecret")
    with pytest.raises(IdentityError):
        register("bob@example.com", "anotherpass")


def test_register_validation(identity_db):
    with pytest.raises(IdentityError):
        register("not-an-email", "supersecret")
    with pytest.raises(IdentityError):
        register("x@example.com", "short")
    with pytest.raises(IdentityError):
        register("y@example.com", "longenough", role="wizard")


def test_password_hashing_zero_dep():
    h = hash_password("hunter2")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_authenticate_ok_and_wrong(identity_db):
    register("carol@example.com", "mypassword")
    out = authenticate("carol@example.com", "mypassword", ip="127.0.0.1")
    assert out["access_token"]
    assert out["refresh_token"]
    assert out["token_type"] == "Bearer"
    assert out["expires_in"] == 900
    assert out["user"]["email"] == "carol@example.com"
    with pytest.raises(IdentityError):
        authenticate("carol@example.com", "badpass")
    with pytest.raises(IdentityError):
        authenticate("nobody@example.com", "anypass")


def test_refresh_and_logout(identity_db):
    register("dave@example.com", "password1")
    out = authenticate("dave@example.com", "password1")
    rt = out["refresh_token"]
    refreshed = refresh(rt)
    assert refreshed["access_token"]
    # 登出后刷新令牌失效
    logout(rt)
    with pytest.raises(IdentityError):
        refresh(rt)


def test_refresh_invalid(identity_db):
    with pytest.raises(IdentityError):
        refresh("")


def test_audit_records(identity_db):
    register("erin@example.com", "password1")
    authenticate("erin@example.com", "password1")
    events = list_audit()
    actions = {e["action"] for e in events}
    assert "register" in actions
    assert "login" in actions


def test_api_register_login_me(logged_in_client):
    """通过 TestClient 走完整注册→登录→/me 链路。"""
    client = logged_in_client.client
    # /me 带令牌返回真实用户
    r = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {logged_in_client.access_token}"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["user"]["email"] == "flow@example.com"
    assert body["role"] == "viewer"


@pytest.fixture
def logged_in_client(identity_db):
    """构造一个已注册的 TestClient，并附上 access_token。"""

    class _Client:
        pass

    from fastapi.testclient import TestClient
    from apps.api.app.main import app

    c = TestClient(app)
    reg = c.post(
        "/v1/auth/register",
        json={"email": "flow@example.com", "password": "password1", "nickname": "Flow"},
    )
    assert reg.status_code == 200
    login = c.post("/v1/auth/login", json={"email": "flow@example.com", "password": "password1"})
    assert login.status_code == 200
    obj = _Client()
    obj.client = c
    obj.access_token = login.json()["data"]["access_token"]
    yield obj


def test_api_anonymous_me_when_no_token(identity_db):
    """开发态（auth_disabled）无令牌 → 匿名 ADMIN。"""
    from fastapi.testclient import TestClient
    from apps.api.app.main import app

    c = TestClient(app)
    r = c.get("/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["data"]["anonymous"] is True


def test_api_rbac_matrix(identity_db):
    from fastapi.testclient import TestClient
    from apps.api.app.main import app

    c = TestClient(app)
    r = c.get("/v1/auth/rbac")
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(row["role"] == "viewer" for row in data["matrix"])


def test_api_refresh_endpoint(identity_db):
    from fastapi.testclient import TestClient
    from apps.api.app.main import app

    c = TestClient(app)
    c.post("/v1/auth/register", json={"email": "g@example.com", "password": "password1"})
    login = c.post("/v1/auth/login", json={"email": "g@example.com", "password": "password1"})
    rt = login.json()["data"]["refresh_token"]
    r = c.post("/v1/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]
