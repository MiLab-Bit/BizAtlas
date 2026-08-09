"""邮箱用户系统服务层（注册/登录/刷新/登出/审计）。

设计：
- 复用 auth/rbac 的 Role 枚举与 issue_token（HMAC，零依赖）签发访问令牌。
- 刷新令牌为随机串，仅存 SHA-256 哈希于 sessions 表。
- 所有写操作经过 data/db 的裸 sqlite 连接，离线确定性，不触网。
- 仅支持邮箱身份（provider='email'）；user_identities 预留 github/wallet。
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
import uuid
from typing import Optional

from bizatlas.auth.rbac import Role, issue_token
from bizatlas.config import get_settings
from bizatlas.data.db import get_connection
from bizatlas.identity.models import User
from bizatlas.identity.passwords import hash_password, verify_password
from bizatlas.identity.email import (
    default_sender,
    build_verification_email,
    build_password_reset_email,
    verification_link,
    reset_link,
)
from bizatlas.tools.permissions import ROLE_SCOPES

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ROLES = {r.value for r in Role}
MIN_PASSWORD_LEN = 8
EMAIL_VERIFY_PURPOSE = "verify_email"
PASSWORD_RESET_PURPOSE = "password_reset"


class IdentityError(Exception):
    """用户系统业务错误（端点层转译为 400/401/409）。"""


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _row_to_user(row) -> User:
    return User(
        id=row["id"],
        public_id=row["public_id"],
        email=row["email"],
        nickname=row["nickname"],
        avatar_url=row["avatar_url"],
        status=row["status"],
        role=row["role"],
        email_verified=bool(row["email_verified"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_user_by_email(email: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),)
        ).fetchone()
    finally:
        conn.close()
    return _row_to_user(row) if row else None


def get_user_by_public_id(public_id: str) -> Optional[User]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE public_id = ?", (public_id,)
        ).fetchone()
    finally:
        conn.close()
    return _row_to_user(row) if row else None


def register(
    email: str,
    password: str,
    nickname: Optional[str] = None,
    role: str = "viewer",
    ip: Optional[str] = None,
    email_sender: object = None,
) -> User:
    """注册邮箱账号（默认 viewer 角色）。重复邮箱 → 409。"""
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise IdentityError("invalid email format")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise IdentityError(f"password too short (min {MIN_PASSWORD_LEN})")
    if role not in VALID_ROLES:
        raise IdentityError(f"invalid role (choose from {sorted(VALID_ROLES)})")

    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise IdentityError("email already registered")
        uid = str(uuid.uuid4())
        public_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            "INSERT INTO users (id, public_id, email, nickname, status, role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
            (uid, public_id, email, nickname, role, now, now),
        )
        conn.execute(
            "INSERT INTO user_identities (id, user_id, provider, identifier, verified_at, created_at) "
            "VALUES (?, ?, 'email', ?, ?, ?)",
            (str(uuid.uuid4()), uid, email, now, now),
        )
        conn.execute(
            "INSERT INTO password_credentials (user_id, password_hash, password_algo, iterations, changed_at) "
            "VALUES (?, ?, 'pbkdf2_sha256', ?, ?)",
            (uid, hash_password(password), 200_000, now),
        )
        conn.commit()
    finally:
        conn.close()
    user = get_user_by_public_id(public_id)
    settings = get_settings()
    if settings.email_verification_enabled:
        # 注册即未验证（email_verified 默认 0），发送验证邮件
        send_verification_email(user, email_sender)
    else:
        # 未启用验证：注册即视为已验证（向后兼容旧演示/测试）
        _set_email_verified(user.id, True)
        user.email_verified = True
    _audit(uid, "register", f"email={email}", ip)
    return user


def authenticate(
    email: str,
    password: str,
    ip: Optional[str] = None,
    device_id: Optional[str] = None,
) -> dict:
    """邮箱+密码登录 → 签发访问/刷新令牌。失败统一抛 IdentityError（401）。"""
    email = (email or "").strip().lower()
    user = get_user_by_email(email)
    if user is None or user.status != "active":
        _audit(None, "login_failed", f"email={email} (no user / inactive)", ip)
        raise IdentityError("invalid credentials")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT password_hash FROM password_credentials WHERE user_id = ?", (user.id,)
        ).fetchone()
    finally:
        conn.close()
    if not row or not verify_password(password, row["password_hash"]):
        _audit(user.id, "login_failed", "bad password", ip)
        raise IdentityError("invalid credentials")

    settings = get_settings()
    if settings.email_verification_enabled and not user.email_verified:
        _audit(user.id, "login_blocked", "email not verified", ip)
        raise IdentityError("email not verified")
    access_token = issue_token(
        user_id=user.public_id,
        role=Role(user.role),
        secret=settings.bizatlas_auth_secret,
        ttl=settings.bizatlas_token_access_ttl,
    )
    refresh_token, refresh_hash = _make_refresh_token()
    expires_at = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + settings.bizatlas_token_refresh_ttl)
    )
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, user_id, refresh_token_hash, device_id, ip_address, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user.id, refresh_hash, device_id, ip, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    _audit(user.id, "login", f"device={device_id or 'web'}", ip)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.bizatlas_token_access_ttl,
        "user": user.to_public(),
    }


def refresh(refresh_token: str, ip: Optional[str] = None) -> dict:
    """用刷新令牌换取新访问令牌。复用同一刷新令牌（未撤销且未过期）。"""
    if not refresh_token:
        raise IdentityError("missing refresh_token")
    refresh_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT s.user_id, s.expires_at, s.revoked_at FROM sessions s "
            "WHERE s.refresh_token_hash = ?",
            (refresh_hash,),
        ).fetchone()
        if not row:
            raise IdentityError("invalid refresh_token")
        if row["revoked_at"]:
            raise IdentityError("refresh_token revoked")
        if time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) > row["expires_at"]:
            raise IdentityError("refresh_token expired")
        user = conn.execute(
            "SELECT * FROM users WHERE id = ? AND status = 'active'", (row["user_id"],)
        ).fetchone()
    finally:
        conn.close()
    if not user:
        raise IdentityError("user inactive")
    settings = get_settings()
    user_obj = _row_to_user(user)
    access_token = issue_token(
        user_id=user_obj.public_id,
        role=Role(user_obj.role),
        secret=settings.bizatlas_auth_secret,
        ttl=settings.bizatlas_token_access_ttl,
    )
    _audit(user_obj.id, "refresh", "", ip)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.bizatlas_token_access_ttl,
        "user": user_obj.to_public(),
    }


def logout(refresh_token: str) -> None:
    """撤销刷新令牌对应的会话。"""
    if not refresh_token:
        return
    refresh_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE refresh_token_hash = ? AND revoked_at IS NULL",
            (_now(), refresh_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _make_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _audit(user_id: Optional[str], action: str, detail: str, ip: Optional[str]) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO audit_log (id, user_id, action, detail, ip_address, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, action, detail, ip, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit(user_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def role_scopes(role: str) -> list[str]:
    """返回某角色拥有的 Scope（供前端展示权限边界）。"""
    r = Role(role) if role in VALID_ROLES else Role.VIEWER
    return sorted(s.value for s in ROLE_SCOPES.get(r, set()))


def _set_email_verified(user_id: str, value: bool) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET email_verified=?, updated_at=? WHERE id=?",
            (1 if value else 0, _now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def _create_email_token(user_id: str, purpose: str, ttl: int | None = None) -> str:
    """生成一次性 token（仅存 SHA-256 哈希），返回原始 token（调用方用于发信）。"""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    ttl = ttl or get_settings().email_token_ttl
    expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + ttl))
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO email_verifications (id, user_id, token_hash, purpose, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, token_hash, purpose, expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return raw


def send_verification_email(user: User, sender: object = None) -> str | None:
    """为用户发送邮箱验证邮件；返回 token（测试用）。无 sender 时仅生成 token 不发信。"""
    sender = sender or default_sender()
    token = _create_email_token(user.id, EMAIL_VERIFY_PURPOSE)
    if sender:
        link = verification_link(token, get_settings().email_base_url)
        subject, html = build_verification_email(link)
        sender.send(user.email, subject, html)
    return token


def verify_email(token: str) -> User:
    """用验证 token 标记邮箱已验证。无效/过期/已用 → IdentityError。"""
    if not token:
        raise IdentityError("missing token")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM email_verifications WHERE token_hash=? AND purpose=?",
            (token_hash, EMAIL_VERIFY_PURPOSE),
        ).fetchone()
        if not row:
            raise IdentityError("invalid token")
        if row["consumed_at"]:
            raise IdentityError("token already used")
        if time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) > row["expires_at"]:
            raise IdentityError("token expired")
        user_row = conn.execute(
            "SELECT public_id FROM users WHERE id=?", (row["user_id"],)
        ).fetchone()
        conn.execute("UPDATE users SET email_verified=1, updated_at=? WHERE id=?", (_now(), row["user_id"]))
        conn.execute(
            "UPDATE user_identities SET verified_at=? WHERE user_id=? AND provider='email'",
            (_now(), row["user_id"]),
        )
        conn.execute("UPDATE email_verifications SET consumed_at=? WHERE id=?", (_now(), row["id"]))
        conn.commit()
    finally:
        conn.close()
    if not user_row:
        raise IdentityError("invalid token")
    return get_user_by_public_id(user_row["public_id"])


def request_password_reset(email: str, sender: object = None) -> str | None:
    """发起密码重置：生成 token 并发邮件。邮箱不存在时返回 None（不泄露账号存在）。"""
    email = (email or "").strip().lower()
    user = get_user_by_email(email)
    if not user:
        return None
    sender = sender or default_sender()
    token = _create_email_token(user.id, PASSWORD_RESET_PURPOSE)
    if sender:
        link = reset_link(token, get_settings().email_base_url)
        subject, html = build_password_reset_email(link)
        sender.send(user.email, subject, html)
    return token


def reset_password(token: str, new_password: str) -> User:
    """用重置 token 更新密码。无效/过期/已用/弱密码 → IdentityError。"""
    if not token:
        raise IdentityError("missing token")
    if len(new_password or "") < MIN_PASSWORD_LEN:
        raise IdentityError(f"password too short (min {MIN_PASSWORD_LEN})")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM email_verifications WHERE token_hash=? AND purpose=?",
            (token_hash, PASSWORD_RESET_PURPOSE),
        ).fetchone()
        if not row:
            raise IdentityError("invalid token")
        if row["consumed_at"]:
            raise IdentityError("token already used")
        if time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) > row["expires_at"]:
            raise IdentityError("token expired")
        user_row = conn.execute(
            "SELECT public_id FROM users WHERE id=?", (row["user_id"],)
        ).fetchone()
        conn.execute(
            "UPDATE password_credentials SET password_hash=?, password_algo='pbkdf2_sha256', "
            "iterations=?, changed_at=? WHERE user_id=?",
            (hash_password(new_password), 200_000, _now(), row["user_id"]),
        )
        conn.execute("UPDATE users SET email_verified=1, updated_at=? WHERE id=?", (_now(), row["user_id"]))
        conn.execute("UPDATE email_verifications SET consumed_at=? WHERE id=?", (_now(), row["id"]))
        conn.commit()
    finally:
        conn.close()
    if not user_row:
        raise IdentityError("invalid token")
    return get_user_by_public_id(user_row["public_id"])
