"""可观测层（阶段 3）测试：结构化日志 / 指标 / 追踪 / observe。"""

from __future__ import annotations

import logging

from bizatlas.observability import observe
from bizatlas.observability.logging import get_logger
from bizatlas.observability.metrics import Metrics
from bizatlas.observability.tracing import current_trace_id, default_tracer, trace


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_structured_logger_fields():
    logger = get_logger("test.struct")
    raw = logging.getLogger("test.struct")
    cap = _Capture()
    raw.addHandler(cap)
    logger.info("hello", foo="bar", n=1)
    assert cap.records
    rec = cap.records[-1]
    assert getattr(rec, "fields", {}) == {"foo": "bar", "n": 1}
    raw.removeHandler(cap)


def test_metrics_counter_gauge_timer():
    m = Metrics()
    m.incr("hits", tags={"path": "/x"})
    m.gauge("queue", 3.0)
    with m.time("op"):
        pass
    snap = m.snapshot()
    assert snap["counters"]["hits{path=\"/x\"}"] == 1
    assert snap["gauges"]["queue"] == 3.0
    assert snap["timers"]["op"]["count"] == 1
    assert "hits" in m.as_prometheus()
    assert "queue" in m.as_prometheus()


def test_tracing_records_span():
    t = default_tracer()
    t.reset()
    with trace("stage_a") as span:
        assert current_trace_id() == span.trace_id
        with trace("stage_b"):
            pass
    spans = t.spans()
    assert len(spans) == 2
    names = {s["name"] for s in spans}
    assert names == {"stage_a", "stage_b"}


def test_observe_records_metrics():
    m = default_tracer  # placeholder to satisfy import; use metrics below
    from bizatlas.observability.metrics import default_metrics

    default_metrics().reset()

    @observe("test.observe_fn")
    def work(x):
        return x + 1

    assert work(1) == 2
    snap = default_metrics().snapshot()
    assert any(k.startswith("test.observe_fn") for k in snap["timers"])
