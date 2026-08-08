"""API 鉴权依赖（FastAPI Depends）。

- 开发态（auth_disabled 或无 secret）：返回匿名 ADMIN 主体，保持旧行为兼容。
- 生产态：从 Authorization: Bearer <token> 解析 Principal；缺失/非法 → 401。
- guard(action)：端点级门禁依赖，未授权 → 403。

令牌由 bizatlas.auth.rbac.issue_token/verify_token（HMAC）签发校验；
生产接入 IdP 时替换 verify 即可，guard 逻辑不变。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException

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


def get_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    settings = get_settings()
    if settings.bizatlas_auth_disabled or not settings.bizatlas_auth_secret:
        return anonymous_admin()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[len("Bearer ") :].strip()
    try:
        return verify_token(token, settings.bizatlas_auth_secret)
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
