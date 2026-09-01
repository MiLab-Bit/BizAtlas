"""API 鉴权依赖（FastAPI Depends）。

- 开发态（auth_disabled 或无 secret）：返回匿名 ADMIN 主体，保持旧行为兼容。
- 生产态：从 Authorization: Bearer <token> 解析 Principal；缺失/非法 → 401。
- guard(action)：端点级门禁依赖，未授权 → 403。

令牌由 bizatlas.auth.rbac.issue_token/verify_token（HMAC）签发校验；
生产接入 IdP 时替换 verify 即可，guard 逻辑不变。
"""

from __future__ import annotations

from typing import Optional

import hashlib

from fastapi import Depends, Header, HTTPException, Request

from bizatlas.auth.rbac import (
    Action,
    PermissionDenied,
    Principal,
    TokenInvalid,
    anonymous_admin,
    require_permission,
    verify_token,
)
from bizatlas.config import get_settings
from bizatlas.identity import apikeys as _apikeys


def get_principal(request: Request, authorization: Optional[str] = Header(default=None)) -> Principal:
    settings = get_settings()
    if settings.bizatlas_auth_disabled or not settings.bizatlas_auth_secret:
        principal = anonymous_admin()
        request.state.principal = principal
        return principal
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[len("Bearer ") :].strip()
    # 1) Agent API Key（机器凭证）：哈希匹配且 active → 以所属账号身份放行
    rec = _apikeys.get_api_key_by_hash(hashlib.sha256(token.encode("utf-8")).hexdigest())
    if rec and rec["status"] == "active":
        _apikeys.touch_api_key(rec["id"])
        owner = _apikeys.principal_for_owner(rec["owner_id"])
        if owner:
            request.state.principal = owner
            return owner
    # 2) 人工 JWT
    try:
        principal = verify_token(token, settings.bizatlas_auth_secret)
        request.state.principal = principal
        return principal
    except TokenInvalid as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def guard(action: Action):
    """返回端点依赖：要求当前主体可执行 action，否则 403。"""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        try:
            require_permission(principal.role, action)
        except PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return principal

    return _dep


def guard_review():
    """复核端点：reviewer/admin 可执行 approve/reject/return。"""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not (principal.can(Action.REVIEW_APPROVE) or principal.can(Action.REVIEW_REJECT)):
            raise HTTPException(
                status_code=403,
                detail=f"role {principal.role.value} 无权执行人工复核",
            )
        return principal

    return _dep


def resolve_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    """严格主体解析（供 /v1/auth/me 使用）：

    - 带 Bearer 令牌：无论 auth_disabled 都校验，无效 → 401（让令牌真实生效）。
    - 无令牌且 auth_disabled：退回匿名 ADMIN（开发态兼容）。
    - 无令牌且鉴权开启：401。
    """
    settings = get_settings()
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        rec = _apikeys.get_api_key_by_hash(hashlib.sha256(token.encode("utf-8")).hexdigest())
        if rec and rec["status"] == "active":
            owner = _apikeys.principal_for_owner(rec["owner_id"])
            if owner:
                return owner
        try:
            return verify_token(token, settings.bizatlas_auth_secret)
        except TokenInvalid as exc:
            raise HTTPException(status_code=401, detail=str(exc))
    if settings.bizatlas_auth_disabled:
        return anonymous_admin()
    raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
