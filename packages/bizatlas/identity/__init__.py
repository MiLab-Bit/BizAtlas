"""身份基础设施（邮箱-only 用户系统）。

对外导出核心服务与模型，供 API 层与测试调用。
"""

from __future__ import annotations

from bizatlas.identity.models import Session, User
from bizatlas.identity.passwords import hash_password, verify_password
from bizatlas.identity.schema import IDENTITY_SCHEMA, init_identity_db
from bizatlas.identity.service import (
    IdentityError,
    authenticate,
    get_user_by_email,
    get_user_by_public_id,
    list_audit,
    logout,
    refresh,
    register,
    role_scopes,
)

__all__ = [
    "Session",
    "User",
    "IDENTITY_SCHEMA",
    "init_identity_db",
    "IdentityError",
    "authenticate",
    "get_user_by_email",
    "get_user_by_public_id",
    "list_audit",
    "logout",
    "refresh",
    "register",
    "role_scopes",
    "hash_password",
    "verify_password",
]
