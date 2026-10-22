from __future__ import annotations

import hmac
import time

from bizatlas.auth.rbac import Action, Principal, Role
from bizatlas.config import get_settings
from bizatlas.contracts.models import Envelope
from bizatlas.data.db import get_connection
from bizatlas.identity import get_user_by_email, get_user_by_public_id, register
from bizatlas.tools.permissions import matrix_summary
from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.app.main import (
    AdminBootstrapRequest,
)
from apps.api.auth_deps import guard
from apps.api.rate_limit import get_client_ip as _client_ip

router = APIRouter()

@router.post("/v1/admin/bootstrap")
def admin_bootstrap(req: AdminBootstrapRequest, request: Request) -> Envelope[dict]:
    """一次性创建/提升首个管理员。仅当系统尚无 admin 时可用，受 BIZATLAS_BOOTSTRAP_TOKEN 保护。

    - 邮箱已存在（非 admin）：直接提升为 admin（并标记邮箱已验证）。
    - 邮箱不存在：以 admin 角色新建（并强制邮箱已验证，便于立即登录）。
    - 已有 admin：返回 409（引导端点自锁，防滥用）。
    """
    settings = get_settings()
    bt = settings.bizatlas_bootstrap_token
    if not bt or not hmac.compare_digest(req.token, bt):
        raise HTTPException(status_code=401, detail="invalid bootstrap token")
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            raise HTTPException(status_code=409, detail="admin already exists; bootstrap disabled")
    finally:
        conn.close()

    email = (req.email or "").strip().lower()
    ip = _client_ip(request)
    existing = get_user_by_email(email)
    now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    if existing:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET role='admin', email_verified=1, updated_at=? WHERE id=?",
                (now_iso, existing.id),
            )
            conn.commit()
        finally:
            conn.close()
        user = get_user_by_public_id(existing.public_id)
        promoted = True
    else:
        if len(req.password or "") < 8:
            raise HTTPException(status_code=400, detail="password too short (min 8)")
        user = register(email, req.password, nickname=req.nickname, role="admin", ip=ip)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET email_verified=1, updated_at=? WHERE email=?",
                (now_iso, email),
            )
            conn.commit()
        finally:
            conn.close()
        user = get_user_by_email(email)
        promoted = False
    return Envelope(
        ok=True,
        data={"user": user.to_public(), "promoted": promoted},
        meta={"degraded": False},
    )

@router.get("/v1/admin/rbac")
def admin_rbac(principal: Principal = Depends(guard(Action.ADMIN))) -> Envelope[dict]:
    """管理端点（阶段 3）：查看角色-权限矩阵，需 admin 权限。"""
    return Envelope(
        ok=True,
        data={
            "matrix": matrix_summary(),
            "roles": [r.value for r in Role],
            "actions": [a.value for a in Action],
        },
        meta={"viewer": principal.user_id},
    )

