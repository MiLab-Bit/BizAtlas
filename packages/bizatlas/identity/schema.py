"""身份基础设施数据库表（邮箱-only 用户系统）。

边界划分（与业务表解耦）：
- users          账号 + 基础资料 + 规范角色（驱动 RBAC Principal）
- user_identities 身份绑定（provider=email 当前唯一；预留 github/wallet 不改动结构）
- password_credentials 密码凭证（pbkdf2_sha256，零外部依赖）
- sessions       访问/刷新令牌会话（refresh_token 仅存哈希）
- audit_log      登录/改密/权限变更等审计事件
- email_verifications 邮箱验证 / 密码找回的一次性 token（仅存哈希）

设计取舍：
- 不引入 ORM，沿用 data/db.py 的裸 sqlite3 + executescript 风格，保持单一迁移入口。
- role 以列形式落在 users 上，作为 RBAC 的权威来源（复用 auth/rbac.Role 枚举
  与 ROLE_SCOPES），避免再建 roles/user_roles 两表造成权限模型漂移。
- 仅支持邮箱登录（无手机号），符合产品初期需求；身份绑定表预留扩展位。
- email_verified 列默认 0：开启邮箱验证时注册即未验证，登录被拦截；
  未开启时注册视为已验证，保持旧演示/测试无感（向后兼容）。
"""

from __future__ import annotations

IDENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  public_id   TEXT UNIQUE NOT NULL,
  email       TEXT UNIQUE NOT NULL,
  nickname    TEXT,
  avatar_url  TEXT,
  status      TEXT NOT NULL DEFAULT 'active',
  role        TEXT NOT NULL DEFAULT 'viewer',
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_identities (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  provider    TEXT NOT NULL,
  identifier  TEXT NOT NULL,
  verified_at TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(provider, identifier)
);

CREATE TABLE IF NOT EXISTS password_credentials (
  user_id       TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  password_algo TEXT NOT NULL,
  iterations    INTEGER NOT NULL,
  changed_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id                TEXT PRIMARY KEY,
  user_id           TEXT NOT NULL,
  refresh_token_hash TEXT NOT NULL,
  device_id         TEXT,
  ip_address        TEXT,
  expires_at        TEXT NOT NULL,
  revoked_at        TEXT,
  created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          TEXT PRIMARY KEY,
  user_id     TEXT,
  action      TEXT NOT NULL,
  detail      TEXT,
  ip_address  TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_verifications (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  token_hash  TEXT UNIQUE NOT NULL,
  purpose     TEXT NOT NULL,   -- verify_email | password_reset
  expires_at  TEXT NOT NULL,
  consumed_at TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_keys (
  id          TEXT PRIMARY KEY,
  owner_id    TEXT NOT NULL,   -- users.public_id（与人工 JWT 的 Principal.user_id 一致）
  name        TEXT NOT NULL,
  key_hash    TEXT NOT NULL,
  prefix      TEXT NOT NULL,
  scopes      TEXT NOT NULL DEFAULT '["*"]',
  status      TEXT NOT NULL DEFAULT 'active',  -- active | revoked
  last_used_at TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  revoked_at  TEXT
);
"""


def init_identity_db(db_path: str | None = None) -> None:
    """创建身份表（幂等）。由 data/db.init_db 调用，复用同一连接策略。"""
    from bizatlas.data.db import get_connection

    conn = get_connection(db_path)
    try:
        conn.executescript(IDENTITY_SCHEMA)
        # 迁移：旧库 users 可能无 email_verified 列（向后兼容，缺则补列）
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "email_verified" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"
            )
        conn.commit()
    finally:
        conn.close()
