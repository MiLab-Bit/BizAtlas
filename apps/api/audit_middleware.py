"""API 审计中间件（P0-② 最小合规）。

对每一个非健康/非公开的 /v1 请求，在响应后写一条 append-only 审计记录：
actor（来自 request.state.principal，由 auth_deps 注入）、动作（METHOD path）、
HTTP 状态、耗时、客户端 IP、request_id。

- 仅记录，不阻断；任何异常静默跳过，不影响业务。
- 与 identity 审计（登录类）共用 audit_log 表，统一审计面。
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from bizatlas.identity.service import audit_api_call

_SKIP_PATHS = {"/v1/healthz", "/v1/health", "/v1/health/live"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        t0 = time.perf_counter()
        response = await call_next(request)
        if path.startswith("/v1/") and path not in _SKIP_PATHS:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            principal = getattr(request.state, "principal", None)
            uid = getattr(principal, "user_id", None) if principal else None
            action = f"{request.method} {path}"
            detail = f"status={response.status_code} latency_ms={dt_ms:.1f}"
            try:
                audit_api_call(
                    uid,
                    action,
                    detail,
                    request.client.host if request.client else None,
                )
            except Exception:  # noqa: BLE001
                # 审计失败绝不影响业务响应
                pass
        return response
