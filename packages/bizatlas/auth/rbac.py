"""企业鉴权 RBAC：Action → Scope 映射、授权判定、主体与令牌。

设计取舍：
- 复用 tools/permissions 的 Role/Scope 作为权限原子，避免两套模型漂移。
- Action 是面向「端点/操作」的语义别名，最终都落到某个 Scope 上校验。
- 令牌采用 HMAC-SHA256（无外部依赖），用于自托管/演示；生产接入 IdP(JWT)
  时只需替换 verify_token，其余 authorize/require_permission 不变。
- 当前主体通过 contextvar 传递，避免把 Principal 层层透传进业务函数。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from bizatlas.tools.permissions import ROLE_SCOPES, Role, Scope


class Action(str, Enum):
    """面向操作的语义动作（端点门禁用）。"""

    ANALYZE = "analyze"                  # 风险研判/报告生成（读）
    REVIEW_APPROVE = "review:approve"   # 通过人工复核
    REVIEW_REJECT = "review:reject"     # 驳回/退回人工复核
    MANAGE_RULES = "rules:manage"       # 规则编译/激活
    MANAGE_COMPANIES = "companies:manage"  # 企业管理类
    EXPORT_REPORTS = "reports:export"   # 落盘导出报告
    TOOL_CALL = "tool:call"             # 调用外部数据源工具
    ADMIN = "admin"                     # 管理类（角色/审计查看）


# Action → 所需 Scope（复用工具治理的权限原子）
ACTION_SCOPE: dict[Action, Scope] = {
    Action.ANALYZE: Scope.DATA_READ,
    Action.REVIEW_APPROVE: Scope.REVIEW_APPROVE,
    Action.REVIEW_REJECT: Scope.REVIEW_REJECT,
    Action.MANAGE_RULES: Scope.MANAGE_RULES,
    Action.MANAGE_COMPANIES: Scope.MANAGE_COMPANIES,
    Action.EXPORT_REPORTS: Scope.EXPORT_REPORTS,
    Action.TOOL_CALL: Scope.TOOL_CALL,
    Action.ADMIN: Scope.ADMIN,
}


class PermissionDenied(Exception):
    """授权失败（端点层转译为 HTTP 403）。"""

    def __init__(self, action: Action, role: Role) -> None:
        self.action = action
        self.role = role
        super().__init__(f"role {role.value} 无权执行 {action.value}")


class TokenInvalid(Exception):
    """令牌缺失/篡改/过期。"""


def authorize(role: Role, action: Action) -> bool:
    """角色是否可执行某动作。"""
    scope = ACTION_SCOPE[action]
    return scope in ROLE_SCOPES.get(role, set())


def require_permission(role: Role, action: Action) -> None:
    """授权硬校验；不满足抛 PermissionDenied。"""
    if not authorize(role, action):
        raise PermissionDenied(action, role)


@dataclass
class Principal:
    """已认证的调用主体。"""

    user_id: str
    role: Role
    scopes: set[Scope] = field(default_factory=set)

    def can(self, action: Action) -> bool:
        return authorize(self.role, action)


_principal_ctx: ContextVar[Principal | None] = ContextVar("bizatlas_principal", default=None)


def set_principal(p: Principal) -> Any:
    return _principal_ctx.set(p)


def get_principal() -> Principal | None:
    return _principal_ctx.get()


def reset_principal(token: Any) -> None:
    _principal_ctx.reset(token)


# —— HMAC 令牌（无外部依赖）——
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: str, role: Role, secret: str, ttl: int = 3600) -> str:
    """签发 HMAC 令牌：<base64url(json)><.><hex(hmac)>。"""
    iat = int(time.time())
    payload = {"uid": user_id, "role": role.value, "iat": iat, "exp": iat + ttl}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str, secret: str) -> Principal:
    """校验 HMAC 令牌并返回 Principal；任何异常 → TokenInvalid。"""
    try:
        if not token or "." not in token:
            raise TokenInvalid("malformed token")
        body, sig = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise TokenInvalid("bad signature")
        payload = json.loads(_b64url_decode(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise TokenInvalid("token expired")
        role = Role(payload["role"])
        return Principal(user_id=payload.get("uid", "unknown"), role=role, scopes=ROLE_SCOPES[role])
    except TokenInvalid:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TokenInvalid(f"token verify failed: {exc}") from exc


def anonymous_admin() -> Principal:
    """开发态/鉴权关闭时的默认主体（拥有全部权限，保持旧行为兼容）。"""
    return Principal(user_id="anonymous", role=Role.ADMIN, scopes=ROLE_SCOPES[Role.ADMIN])
