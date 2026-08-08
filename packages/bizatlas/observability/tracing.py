"""分布式追踪骨架（零依赖）：trace_id / span_id / 父子关系 + 收集。

企业环境下用于把一次请求穿越的多个内部阶段（研判/检索/写作/工具调用）
串成一条链路，定位慢路径。这里做进程内轻量收集；接入 OpenTelemetry 时
只需把 collect 换成 exporter，Span 结构可直接映射。
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_trace_id_ctx: ContextVar[str | None] = ContextVar("bizatlas_trace_id", default=None)
_span_id_ctx: ContextVar[str | None] = ContextVar("bizatlas_span_id", default=None)


class Span:
    def __init__(self, trace_id: str, span_id: str, parent_id: str | None, name: str) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_id = parent_id
        self.name = name
        self.start = time.perf_counter()
        self.end: float | None = None
        self.ok = True
        self.tags: dict[str, Any] = {}

    def finish(self, ok: bool = True) -> None:
        self.end = time.perf_counter()
        self.ok = ok

    def duration(self) -> float:
        if self.end is None:
            return 0.0
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "duration": round(self.duration(), 6),
            "ok": self.ok,
            "tags": self.tags,
        }


class Tracer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: list[Span] = []

    def start_span(self, name: str, parent_id: str | None = None) -> Span:
        trace_id = _trace_id_ctx.get() or uuid.uuid4().hex
        span = Span(trace_id, uuid.uuid4().hex[:12], parent_id or "root", name)
        with self._lock:
            self._spans.append(span)
        return span

    def spans(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans]

    def latest_trace_id(self) -> str | None:
        with self._lock:
            return self._spans[-1].trace_id if self._spans else None

    def reset(self) -> None:
        with self._lock:
            self._spans.clear()


_default_tracer = Tracer()


def default_tracer() -> Tracer:
    return _default_tracer


@contextmanager
def trace(name: str, tracer: Tracer | None = None, **tags: Any) -> Any:
    """上下文管理器：开启一个 span 并链接到当前 trace。"""
    t = tracer or _default_tracer
    parent = _span_id_ctx.get()
    span = t.start_span(name, parent_id=parent)
    span.tags.update(tags)
    token_trace = _trace_id_ctx.set(span.trace_id)
    token_span = _span_id_ctx.set(span.span_id)
    try:
        yield span
    except Exception:
        span.finish(ok=False)
        raise
    else:
        span.finish(ok=True)
    finally:
        _trace_id_ctx.reset(token_trace)
        _span_id_ctx.reset(token_span)


def current_trace_id() -> str | None:
    return _trace_id_ctx.get()
