"""熔断器（Circuit Breaker）：防止外部工具/后端故障引发雪崩。

状态机（与经典模式一致）：
- closed：正常放行；连续失败达到阈值 → 打开（open）。
- open：直接拒绝调用（快速失败），避免无谓重试拖垮调用方。
- half-open：冷却时间过后放行一次探测；成功达到阈值 → 闭合；
  任一次失败 → 重新打开。

所有状态按 name 集中登记，装饰器与治理调用共享同一实例，便于统一观测。
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

_BREAKERS: dict[str, "CircuitBreaker"] = {}


class CircuitOpen(Exception):
    """熔断器处于 open/half-open 探测失败时的快速失败异常。"""

    def __init__(self, name: str, cooldown_remaining: float) -> None:
        self.name = name
        self.cooldown_remaining = cooldown_remaining
        super().__init__(
            f"circuit '{name}' is open (cooldown remaining {cooldown_remaining:.1f}s)"
        )


class CircuitBreaker:
    """单个工具的熔断器。线程安全（用实例锁保护状态计数）。"""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        cooldown: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.success_threshold = success_threshold
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._state = "closed"
        self._opened_at = 0.0
        self.total_calls = 0
        self.total_rejected = 0
        self.total_failures = 0

    # —— 状态推导 ——
    @property
    def state(self) -> str:
        if self._state == "open":
            if time.monotonic() - self._opened_at >= self.cooldown:
                return "half_open"
            return "open"
        return self._state

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = time.monotonic()
        self._consecutive_failures = 0
        self._consecutive_successes = 0

    def _on_failure(self) -> None:
        self.total_failures += 1
        if self._state == "half_open":
            self._open()
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._open()

    def _on_success(self) -> None:
        if self._state == "half_open":
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self._state = "closed"
                self._consecutive_failures = 0
                self._consecutive_successes = 0
        else:
            self._consecutive_failures = 0

    def allow(self) -> bool:
        """当前是否允许放行一次调用。"""
        return self.state != "open"

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.total_calls += 1
        # 冷却结束后，把派生态 half_open 落实为真实状态，后续成功/失败判定才正确
        if self._state == "open" and (time.monotonic() - self._opened_at) >= self.cooldown:
            self._state = "half_open"
            self._consecutive_successes = 0
        if not self.allow():
            self.total_rejected += 1
            remaining = self.cooldown - (time.monotonic() - self._opened_at)
            raise CircuitOpen(self.name, max(0.0, remaining))
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        self._on_success()
        return result

    def reset(self) -> None:
        """手动复位（运维/测试用）。"""
        self._state = "closed"
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._opened_at = 0.0

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "total_calls": self.total_calls,
            "total_rejected": self.total_rejected,
            "total_failures": self.total_failures,
        }


def get_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    cooldown: float = 30.0,
    success_threshold: int = 2,
) -> CircuitBreaker:
    """按 name 获取（或惰性创建）熔断器，全局共享。"""
    br = _BREAKERS.get(name)
    if br is None:
        br = CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            cooldown=cooldown,
            success_threshold=success_threshold,
        )
        _BREAKERS[name] = br
    return br


def circuit(
    name: str,
    *,
    failure_threshold: int = 5,
    cooldown: float = 30.0,
    success_threshold: int = 2,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：为函数套上按 name 登记的熔断器。"""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        br = get_breaker(
            name,
            failure_threshold=failure_threshold,
            cooldown=cooldown,
            success_threshold=success_threshold,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return br.call(fn, *args, **kwargs)

        wrapper._breaker = br  # type: ignore[attr-defined]
        return wrapper

    return deco
