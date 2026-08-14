"""Agent API Key（机器凭证）—— 与 Cardio 同一套逻辑。

- 明文 Key 仅创建/轮换瞬间返回一次，库内只存 SHA-256 哈希。
- owner_id 引用 users.public_id（与人工 JWT 的 Principal.user_id 一致）。
- 支持创建/列表/轮换/撤销；status=revoked 立即失效（鉴权实时查库）。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from typing import Any, Optional

from bizatlas.data.db import get_connection


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def generate_api_key(prefix: str = "ba_") -> tuple[str, str, str]:
    """返回 (明文, 前缀, 哈希)。"""
    raw = secrets.token_urlsafe(32)
    plain = f"{prefix}{raw}"
    return plain, prefix, hashlib.sha256(plain.encode("utf-8")).hexdigest()


def hash_api_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def create_api_key(owner_id: str, name: str, key_hash: str, prefix: str, scopes: list[str]) -> str:
    kid = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO api_keys (id, owner_id, name, key_hash, prefix, scopes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kid, owner_id, name, key_hash, prefix, json.dumps(scopes, ensure_ascii=False), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return kid


def list_api_keys(owner_id: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, prefix, scopes, status, last_used_at, created_at, revoked_at "
            "FROM api_keys WHERE owner_id=? ORDER BY created_at DESC",
            (owner_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"], "name": r["name"], "prefix": r["prefix"],
            "scopes": json.loads(r["scopes"] or "[]"), "status": r["status"],
            "last_used_at": r["last_used_at"], "created_at": r["created_at"], "revoked_at": r["revoked_at"],
        }
        for r in rows
    ]


def get_api_key_by_hash(key_hash: str) -> Optional[dict[str, Any]]:
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT id, owner_id, status, scopes FROM api_keys WHERE key_hash=?", (key_hash,)
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {
        "id": r["id"], "owner_id": r["owner_id"], "status": r["status"],
        "scopes": json.loads(r["scopes"] or "[]"),
    }


def rotate_api_key(key_id: str, owner_id: str, key_hash: str, prefix: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE api_keys SET key_hash=?, prefix=?, status='active', revoked_at=NULL "
            "WHERE id=? AND owner_id=?",
            (key_hash, prefix, key_id, owner_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def revoke_api_key(key_id: str, owner_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE api_keys SET status='revoked', revoked_at=? WHERE id=? AND owner_id=?",
            (_now(), key_id, owner_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def touch_api_key(key_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (_now(), key_id))
        conn.commit()
    finally:
        conn.close()


def principal_for_owner(public_id: str):
    """为 API Key 所属账号构造 RBAC Principal（user_id 与人工 JWT 一致）。"""
    from bizatlas.auth.rbac import Principal, Role, ROLE_SCOPES

    conn = get_connection()
    try:
        r = conn.execute("SELECT role FROM users WHERE public_id=?", (public_id,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    role = Role(r["role"])
    return Principal(user_id=public_id, role=role, scopes=ROLE_SCOPES[role])
