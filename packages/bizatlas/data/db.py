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
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    settings = get_settings()
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
        conn.commit()
    finally:
        conn.close()
    return path
