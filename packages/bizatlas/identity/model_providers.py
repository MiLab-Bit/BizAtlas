"""用户自带大模型供应商密钥存储（加密落库）。

与机器凭证 api_keys 解耦：本表只存用户自填的 provider + key（Fernet 加密），
供前端「模型配置」使用，并可经 /v1/auth/model-providers/test 直连供应商验证可用性。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from bizatlas.data.db import get_connection
from bizatlas.identity.crypto import decrypt, encrypt


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def create_model_provider(owner_id: str, name: str, provider: str, api_key: str,
                          base_url: Optional[str], model: Optional[str],
                          slot: str = "text") -> str:
    """创建一条用户自带大模型供应商配置（加密落库）。
    slot: 'text'（文本模型）或 'multimodal'（多模态模型），同一用户每槽位各一条。
    """
    pid = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO model_providers "
            "(id, owner_id, slot, name, provider, api_key_enc, base_url, model, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, owner_id, slot, name, provider, encrypt(api_key), base_url, model,
             "unverified", _now(), _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def list_model_providers(owner_id: str) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, slot, name, provider, base_url, model, status, last_error, last_tested_at, created_at "
            "FROM model_providers WHERE owner_id=? ORDER BY slot, created_at DESC",
            (owner_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_model_provider(pid: str, owner_id: str) -> Optional[dict[str, Any]]:
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT * FROM model_providers WHERE id=? AND owner_id=?", (pid, owner_id)
        ).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def get_active_provider(owner_id: str, slot: str = "text") -> Optional[dict[str, Any]]:
    """取该用户在指定槽位（'text' 文本 / 'multimodal' 多模态）最近一条 active 配置。
    供对话/分析实际调用大模型时按任务选槽使用。无则返回 None（调用方回退平台设置）。
    """
    conn = get_connection()
    try:
        r = conn.execute(
            "SELECT id FROM model_providers WHERE owner_id=? AND slot=? AND status='active' "
            "ORDER BY updated_at DESC LIMIT 1",
            (owner_id, slot),
        ).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    rec = get_model_provider(r["id"], owner_id)
    if not rec:
        return None
    return {
        "id": rec["id"],
        "owner_id": rec["owner_id"],
        "name": rec["name"],
        "provider": rec["provider"],
        "api_key": decrypt(rec["api_key_enc"]),
        "base_url": rec["base_url"],
        "model": rec["model"],
        "status": rec["status"],
    }


def get_active_model_provider(owner_id: str) -> Optional[dict[str, Any]]:
    """兼容别名：默认取 text 槽位 active 配置（供既有调用方使用，无需改动）。"""
    return get_active_provider(owner_id, "text")


def update_status(pid: str, owner_id: str, status: str,
                  last_error: Optional[str], last_tested_at: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE model_providers SET status=?, last_error=?, last_tested_at=?, updated_at=? "
            "WHERE id=? AND owner_id=?",
            (status, last_error, last_tested_at, _now(), pid, owner_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_model_provider(pid: str, owner_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM model_providers WHERE id=? AND owner_id=?", (pid, owner_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
