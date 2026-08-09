"""身份领域模型（轻量 dataclass，非 ORM）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: str
    public_id: str
    email: str
    nickname: Optional[str]
    avatar_url: Optional[str]
    status: str
    role: str  # RBAC 角色值：viewer/analyst/reviewer/admin
    email_verified: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_public(self) -> dict:
        """对外暴露的安全字段（不含密码/内部 id）。"""
        return {
            "user_id": self.public_id,
            "email": self.email,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "status": self.status,
            "role": self.role,
            "email_verified": self.email_verified,
            "created_at": self.created_at,
        }


@dataclass
class Session:
    id: str
    user_id: str
    device_id: Optional[str]
    ip_address: Optional[str]
    expires_at: str
    revoked_at: Optional[str]
    created_at: str
