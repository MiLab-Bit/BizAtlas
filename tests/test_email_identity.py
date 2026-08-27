"""邮箱验证 / 密码找回离线测试（注入 ConsoleEmailSender，不触网）。

隔离策略：conftest 已把 EMAIL_VERIFICATION_ENABLED / SMTP_ENABLED 强制为 false，
保护默认离线行为。本文件需要验证相关逻辑时，在用例内用 os.environ 重新启用，
并注入 fake sender，避免真实发信；用例结束在 finally 中恢复环境变量并清 settings 缓存。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from bizatlas.config import get_settings
from bizatlas.data.db import get_connection, init_db
from bizatlas.identity import (
    IdentityError,
    authenticate,
    register,
    request_password_reset,
    reset_password,
    send_verification_email,
    verify_email,
)
from bizatlas.identity.email import ConsoleEmailSender


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


def _enable_verification() -> None:
    os.environ["EMAIL_VERIFICATION_ENABLED"] = "true"
    get_settings.cache_clear()


def _disable_verification() -> None:
    # 显式设回 false（覆盖 .env 中可能为 true 的值），避免污染后续用例
    os.environ["EMAIL_VERIFICATION_ENABLED"] = "false"
    get_settings.cache_clear()


def test_register_default_verified(identity_db):
    """默认（验证关闭）：注册即已验证，登录无感（向后兼容）。"""
    u = register("alice@example.com", "supersecret")
    assert u.email_verified is True
    out = authenticate("alice@example.com", "supersecret")
    assert out["access_token"]


def test_verification_flow_blocks_login(identity_db):
    """开启验证：注册即未验证并收到邮件；未验证登录被拦截；验证后可登录；token 一次性。"""
    _enable_verification()
    try:
        fake = ConsoleEmailSender()
        u = register("bob@example.com", "supersecret", email_sender=fake)
        assert u.email_verified is False
        assert len(fake.sent) == 1

        # 未验证登录被拦截
        with pytest.raises(IdentityError):
            authenticate("bob@example.com", "supersecret")

        # 取出 token 完成验证
        token = fake.last_token()
        assert token
        v = verify_email(token)
        assert v.email_verified is True

        # 验证后可登录
        out = authenticate("bob@example.com", "supersecret")
        assert out["access_token"]

        # token 重复使用失效
        with pytest.raises(IdentityError):
            verify_email(token)
    finally:
        _disable_verification()


def test_verify_invalid_token(identity_db):
    with pytest.raises(IdentityError):
        verify_email("garbage-token")


def test_password_reset_flow(identity_db):
    """密码找回：注册（未验证）→ 请求重置（发信）→ 用 token 改密 → 旧密码失效/新密码可用。"""
    _enable_verification()
    try:
        fake = ConsoleEmailSender()
        register("carol@example.com", "oldpassword", email_sender=fake)
        tok = request_password_reset("carol@example.com", sender=fake)
        assert tok
        # 注册验证邮件 + 重置邮件
        assert len(fake.sent) == 2

        new = reset_password(tok, "newpassword123")
        assert new.email_verified is True
        with pytest.raises(IdentityError):
            authenticate("carol@example.com", "oldpassword")
        out = authenticate("carol@example.com", "newpassword123")
        assert out["access_token"]

        # token 重复使用失效
        with pytest.raises(IdentityError):
            reset_password(tok, "another123")
    finally:
        _disable_verification()


def test_password_reset_weak(identity_db):
    _enable_verification()
    try:
        register("dave@example.com", "supersecret")
        tok = request_password_reset("dave@example.com")
        with pytest.raises(IdentityError):
            reset_password(tok, "short")
    finally:
        _disable_verification()


def test_password_reset_expired(identity_db):
    _enable_verification()
    try:
        register("erin@example.com", "supersecret")
        tok = request_password_reset("erin@example.com")
        # 手动令 token 过期
        conn = get_connection()
        conn.execute(
            "UPDATE email_verifications SET expires_at='2000-01-01 00:00:00' WHERE purpose='password_reset'"
        )
        conn.commit()
        conn.close()
        with pytest.raises(IdentityError):
            reset_password(tok, "newpassword123")
    finally:
        _disable_verification()


def test_request_password_reset_unknown_email(identity_db):
    """邮箱不存在时静默返回 None（不泄露账号是否存在）。"""
    _enable_verification()
    try:
        assert request_password_reset("nobody@example.com", sender=ConsoleEmailSender()) is None
    finally:
        _disable_verification()
