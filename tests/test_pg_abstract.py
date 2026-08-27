"""数据库连接层抽象测试：默认 SQLite 行为不变；DSN 识别 postgres 分支。"""

from bizatlas.data.db import get_connection, resolve_db_backend


def test_backend_default_sqlite():
    assert resolve_db_backend("") == "sqlite"
    assert resolve_db_backend(None) == "sqlite"


def test_backend_postgres_detection():
    assert resolve_db_backend("postgresql://u:p@h/db") == "postgres"
    assert resolve_db_backend("postgres://u:p@h/db") == "postgres"


def test_default_connection_sqlite():
    conn = get_connection()
    try:
        assert conn is not None
    finally:
        conn.close()
