"""指标采集（零依赖）：计数器 / 计时直方图 / 仪表，线程安全。

提供：
- incr / gauge：累计量与瞬时量（按 name+tags 维度）。
- time(name)：上下文管理器，记录耗时直方图（count/sum/avg/p95/max）。
- snapshot()：结构化快照，供 /v1/metrics 返回。
- as_prometheus()：Prometheus 文本 exposition 格式（可直接被 Prometheus 抓取）。

进程级默认收集器 _default_metrics，中间件/observe 共享同一份。
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator


def _tag_key(tags: dict[str, str] | None) -> str:
    if not tags:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(tags.items())) + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, list[float]] = defaultdict(list)

    def incr(self, name: str, amount: int = 1, tags: dict[str, str] | None = None) -> None:
        key = name + _tag_key(tags)
        with self._lock:
            self._counters[key] += amount

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        key = name + _tag_key(tags)
        with self._lock:
            self._gauges[key] = value

    def record(self, name: str, seconds: float, tags: dict[str, str] | None = None) -> None:
        """直接记录一次耗时样本（供中间件等非上下文场景使用）。"""
        key = name + _tag_key(tags)
        with self._lock:
            self._timers[key].append(seconds)

    @contextmanager
    def time(self, name: str, tags: dict[str, str] | None = None) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            key = name + _tag_key(tags)
            with self._lock:
                self._timers[key].append(dt)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            timers: dict[str, Any] = {}
            for k, vals in self._timers.items():
                if not vals:
                    continue
                vals_sorted = sorted(vals)
                n = len(vals_sorted)
                p95 = vals_sorted[min(n - 1, int(math.ceil(0.95 * n)) - 1)]
                timers[k] = {
                    "count": n,
                    "sum": round(sum(vals_sorted), 6),
                    "avg": round(sum(vals_sorted) / n, 6),
                    "p95": round(p95, 6),
                    "max": round(vals_sorted[-1], 6),
                }
            return {"counters": counters, "gauges": gauges, "timers": timers}

    def as_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for key, val in self._counters.items():
                name = key.split("{")[0]
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{key} {val}")
            for key, val in self._gauges.items():
                name = key.split("{")[0]
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{key} {val}")
            for key, vals in self._timers.items():
                if not vals:
                    continue
                name = key.split("{")[0]
                lines.append(f"# TYPE {name} histogram")
                lines.append(f'{key}_count {len(vals)}')
                lines.append(f'{key}_sum {round(sum(vals), 6)}')
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()


_default_metrics = Metrics()


def default_metrics() -> Metrics:
    return _default_metrics
