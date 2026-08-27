"""可观测层（阶段 3）：结构化日志 + 指标 + 追踪，统一 observe 装饰器。

observe 把一次业务调用同时：打点计时（metrics）、开一个 span（tracing）、
记一条结构化日志（logging），并把 request_id 自动带进日志与追踪上下文。
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from bizatlas.observability.logging import (
    get_logger,
    get_request_id,
    log,
    new_request_id,
    set_request_id,
)
from bizatlas.observability.metrics import default_metrics
from bizatlas.observability.tracing import current_trace_id, default_tracer, trace


def observe(
    name: str | None = None,
    tags: dict[str, str] | None = None,
    tracer: Any = None,
    metrics: Any = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：组合 计时 + 追踪 + 结构化日志。"""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        metric_name = name or f"fn.{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            m = metrics or default_metrics()
            t = tracer or default_tracer()
            logger = get_logger("bizatlas.observe")
            with trace(metric_name, tracer=t), m.time(metric_name, tags=tags):
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "observe.error",
                        fn=metric_name,
                        trace_id=current_trace_id(),
                        error=type(exc).__name__,
                    )
                    raise
                logger.debug(
                    "observe.ok",
                    fn=metric_name,
                    trace_id=current_trace_id(),
                    request_id=get_request_id(),
                )
                return result

        return wrapper

    return deco


__all__ = [
    "current_trace_id",
    "default_metrics",
    "default_tracer",
    "get_logger",
    "get_request_id",
    "log",
    "new_request_id",
    "observe",
    "set_request_id",
    "trace",
]
