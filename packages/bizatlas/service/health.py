"""服务健康探针（高可用骨架）。

- liveness：进程还活着（kube/Docker 的 Liveness 探针用），只做极轻量自检。
- readiness：依赖就绪（DB 可连接、核心模块可导入），未就绪则流量不应打入。
- 版本来自 bizatlas.__version__，统一治理口径。

两者分离是 Kubernetes/容器编排的标准做法：liveness 失败=重启，
readiness 失败=摘流量不重启。
"""

from __future__ import annotations

from typing import Any

from bizatlas import __version__
from bizatlas.config import get_settings


def liveness() -> dict[str, Any]:
    return {
        "status": "up",
        "service": "bizatlas-api",
        "version": __version__,
    }


def readiness() -> dict[str, Any]:
    settings = get_settings()
    db_ok = True
    db_error = ""
    try:
        from bizatlas.data.db import init_db

        init_db()
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = str(exc)

    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "service": "bizatlas-api",
        "version": __version__,
        "db_ok": db_ok,
        "db_error": db_error,
        "mode": settings.bizatlas_mode,
    }
