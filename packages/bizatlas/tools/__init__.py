"""工具治理骨架（阶段 3）。

把商舆的「重/外部」能力统一纳入：权限（Role/Scope 最小权限）、熔断
（防止外部后端故障雪崩）、沙箱（隔离子进程、强超时+内存上限）三道防线，
统一以 ToolResult 信封返回，失败显式披露，绝不静默。
"""

from bizatlas.tools.base import ToolResult
from bizatlas.tools.builtins import register_default_tools
from bizatlas.tools.circuit import CircuitBreaker, CircuitOpen, circuit, get_breaker
from bizatlas.tools.permissions import (
    AccessDenied,
    Role,
    Scope,
    matrix_summary,
    require_scope,
    role_has_scope,
    scopes_of,
)
from bizatlas.tools.registry import ToolRegistry, ToolSpec, default_registry, govern
from bizatlas.tools.sandbox import SandboxError, SandboxTimeout, run_in_sandbox

__all__ = [
    "AccessDenied",
    "CircuitBreaker",
    "CircuitOpen",
    "Role",
    "Scope",
    "SandboxError",
    "SandboxTimeout",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "circuit",
    "default_registry",
    "govern",
    "get_breaker",
    "matrix_summary",
    "register_default_tools",
    "require_scope",
    "role_has_scope",
    "run_in_sandbox",
    "scopes_of",
]
