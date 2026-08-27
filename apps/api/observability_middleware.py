"""API 可观测中间件：请求 ID / 计数 / 耗时 / 结构化访问日志。"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from bizatlas.observability.logging import get_logger, new_request_id, set_request_id
from bizatlas.observability.metrics import default_metrics


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or new_request_id()
        set_request_id(rid)
        m = default_metrics()
        path = request.url.path
        m.incr("http_requests_total", tags={"method": request.method})

        logger = get_logger("bizatlas.http")
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            m.incr("http_errors_total", tags={"method": request.method})
            logger.error("http.error", request_id=rid, path=path)
            raise
        dt = time.perf_counter() - t0
        m.incr("http_responses_total", tags={"status": str(response.status_code)})
        m.record("http_request_duration_seconds", dt, tags={"path": path})
        logger.info(
            "http.access",
            request_id=rid,
            path=path,
            method=request.method,
            status=response.status_code,
            duration=round(dt, 4),
        )
        response.headers["X-Request-ID"] = rid
        return response
