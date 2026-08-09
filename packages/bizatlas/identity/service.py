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
from bizatlas.tools.permissions import ROLE_SCOPES

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ROLES = {r.value for r in Role}
MIN_PASSWORD_LEN = 8


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
    _audit(uid, "register", f"email={email}", ip)
    return get_user_by_public_id(public_id)


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
