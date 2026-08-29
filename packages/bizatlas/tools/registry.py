"""工具注册表 + 治理调用：把「权限校验 → 熔断 → 沙箱」串成一条可审计的链路。

工具治理的三道防线：
1. 权限（require_scope）：角色缺少 Scope 直接拒绝，返回显式披露。
2. 熔断（CircuitBreaker）：外部后端连续失败 → 快速失败，防雪崩。
3. 沙箱（run_in_sandbox）：重/外部工具在隔离子进程跑，强超时+内存上限。

治理调用统一返回 ToolResult 信封，失败永远走 disclosures 而非异常吞没。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from bizatlas.agents.base import Disclosure
from bizatlas.tools.base import ToolResult
from bizatlas.tools.circuit import CircuitOpen, get_breaker
from bizatlas.tools.permissions import AccessDenied, Role, Scope, require_scope
from bizatlas.tools.sandbox import SandboxError, SandboxTimeout, run_in_sandbox


@dataclass
class ToolSpec:
    """一个受治理工具的注册描述。"""

    name: str
    scope: Scope
    fn: Callable[..., Any]
    timeout: float = 5.0
    use_sandbox: bool = False
    description: str = ""


class ToolRegistry:
    """工具注册表：登记工具并按 Role 治理地调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return [t for t in self._tools.values()]

    def call(self, name: str, role: Role, *args: Any, **kwargs: Any) -> ToolResult:
        spec = self.get(name)
        if spec is None:
            return ToolResult.failed("tool_missing", f"未注册工具：{name}")

        # 1) 权限校验
        try:
            require_scope(role, spec.scope)
        except AccessDenied as exc:
            return ToolResult.denied(str(exc))

        # 2) 熔断 + 3) 沙箱
        breaker = get_breaker(name)
        try:
            if spec.use_sandbox:
                raw = run_in_sandbox(spec.fn, *args, timeout=spec.timeout, **kwargs)
            else:
                raw = breaker.call(spec.fn, *args, **kwargs)
        except CircuitOpen as exc:
            return ToolResult.failed("circuit_open", str(exc))
        except SandboxTimeout as exc:
            return ToolResult.failed("sandbox_timeout", str(exc))
        except SandboxError as exc:
            return ToolResult.failed("sandbox_error", str(exc))
        except Exception as exc:  # noqa: BLE001
            return ToolResult.failed("tool_error", f"{type(exc).__name__}: {exc}")

        return ToolResult(ok=True, output=raw, meta={"circuit": breaker.state})

    def has(self, name: str) -> bool:
        return name in self._tools


# 进程级默认注册表（应用启动时用 register_default_tools 填充）
_default_registry = ToolRegistry()


def default_registry() -> ToolRegistry:
    return _default_registry


def govern(
    name: str,
    scope: Scope,
    *,
    timeout: float = 5.0,
    use_sandbox: bool = False,
    description: str = "",
    registry: ToolRegistry | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """装饰器：把函数登记为受治理工具（权限+熔断+沙箱）。"""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        (registry or _default_registry).register(
            ToolSpec(
                name=name,
                scope=scope,
                fn=fn,
                timeout=timeout,
                use_sandbox=use_sandbox,
                description=description,
            )
        )
        return fn

    return deco
