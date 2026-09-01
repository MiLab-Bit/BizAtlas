from __future__ import annotations

import sqlite3
from pathlib import Path

from bizatlas.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  industry TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  status TEXT DEFAULT 'uploaded',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  chunk_index INTEGER,
  content TEXT,
  page INTEGER,
  FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS financial_statements (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  period TEXT,
  statement_type TEXT,
  payload_json TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS financial_metrics (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL,
  unit TEXT,
  tier TEXT,
  as_of TEXT,
  source_json TEXT,
  evidence_refs TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS entities_relations (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  src TEXT,
  rel TEXT,
  dst TEXT,
  props_json TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS rules (
  id TEXT PRIMARY KEY,
  name TEXT,
  dimension TEXT,
  payload_json TEXT,
  version TEXT,
  status TEXT
);

CREATE TABLE IF NOT EXISTS rule_hits (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  rule_id TEXT,
  payload_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_scores (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  grade TEXT,
  score REAL,
  payload_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  template_id TEXT,
  status TEXT,
  payload_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  company_id TEXT,
  level TEXT,
  message TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  provider_id TEXT,
  company_key TEXT,
  tier TEXT,
  ok INTEGER,
  message TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  template_id TEXT NOT NULL,
  company_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  source_type TEXT,
  doc_id TEXT,
  page INTEGER,
  bbox TEXT,
  doc_sha256 TEXT,
  content_snippet TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS model_providers (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  slot TEXT NOT NULL DEFAULT 'text',
  name TEXT NOT NULL,
  provider TEXT NOT NULL,
  api_key_enc TEXT NOT NULL,
  base_url TEXT,
  model TEXT,
  status TEXT NOT NULL DEFAULT 'unverified',
  last_error TEXT,
  last_tested_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_events (
  id TEXT PRIMARY KEY,
  report_id TEXT,
  company_id TEXT,
  analyst TEXT,
  action TEXT NOT NULL,
  decision TEXT,
  comment TEXT,
  latency_ms REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


"""


def resolve_db_backend(dsn: str | None = None) -> str:
    """返回当前数据库后端：'sqlite'（默认）或 'postgres'（DSN 以 postgresql:// 开头）。

    连接层抽象入口：部署到托管 PG 时填 bizatlas_db_dsn，但 SQLite→PG 的 DDL /
    数据迁移需在部署环境执行（两者语法不兼容），本函数仅做后端识别与分流。
    """
    dsn = dsn or get_settings().bizatlas_db_dsn
    if dsn and (dsn.startswith("postgresql://") or dsn.startswith("postgres://")):
        return "postgres"
    return "sqlite"


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    settings = get_settings()
    if resolve_db_backend() == "postgres":
        # PG 后端：需在部署环境安装 psycopg 并执行 SQLite→PG 迁移（DDL 不兼容）。
        raise NotImplementedError(
            "PostgreSQL 后端尚未启用：请在部署环境安装 psycopg 并提供迁移脚本"
        )
    path = Path(db_path or settings.bizatlas_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> Path:
    settings = get_settings()
    path = Path(db_path or settings.bizatlas_db_path)
    conn = get_connection(str(path))
    try:
        conn.executescript(SCHEMA)
        # 轻量迁移：CREATE TABLE IF NOT EXISTS 不会改动旧表结构，
        # 新增列用 ALTER 补（列已存在时静默跳过）。
        try:
            conn.execute("ALTER TABLE financial_metrics ADD COLUMN evidence_refs TEXT")
        except sqlite3.OperationalError:
            pass
        # 双模型槽位：已存在的 model_providers 表补齐 slot 列（默认 'text'）
        try:
            conn.execute("ALTER TABLE model_providers ADD COLUMN slot TEXT NOT NULL DEFAULT 'text'")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()
    # 身份基础设施表（邮箱用户系统）：幂等，独立迁移入口。
    from bizatlas.identity.schema import init_identity_db

    init_identity_db(str(path))
    return path
