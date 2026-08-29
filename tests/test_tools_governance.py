"""工具治理骨架（阶段 3）测试。

覆盖：
- 权限矩阵：角色→Scope 最小权限
- 注册表治理调用：权限拒绝 / 正常执行
- 熔断器三态：closed → open（连续失败）→ half_open → closed（恢复）
- 沙箱：超时强杀 / 异常透传 / 正常返回
"""

from __future__ import annotations

import pytest

from bizatlas.tools.circuit import CircuitBreaker, CircuitOpen, get_breaker
from bizatlas.tools.permissions import (
    AccessDenied,
    Role,
    Scope,
    require_scope,
    role_has_scope,
)
from bizatlas.tools.registry import ToolRegistry, ToolSpec
from bizatlas.tools.sandbox import SandboxTimeout, run_in_sandbox
from bizatlas.tools.sandbox import _demo_fail, _demo_ok, _demo_slow


# —— 权限矩阵 ——
def test_role_scope_matrix():
    assert role_has_scope(Role.ADMIN, Scope.ADMIN)
    assert role_has_scope(Role.VIEWER, Scope.DATA_READ)
    assert not role_has_scope(Role.VIEWER, Scope.DATA_WRITE)
    assert not role_has_scope(Role.ANALYST, Scope.REVIEW_APPROVE)
    assert role_has_scope(Role.REVIEWER, Scope.REVIEW_APPROVE)
    assert role_has_scope(Role.REVIEWER, Scope.REVIEW_REJECT)
    # 最小权限：viewer 只有读
    assert set(s for s in Scope if role_has_scope(Role.VIEWER, s)) == {Scope.DATA_READ}


def test_require_scope_raises():
    with pytest.raises(AccessDenied):
        require_scope(Role.VIEWER, Scope.DATA_WRITE)


# —— 注册表治理调用 ——
def test_registry_permission_denied():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="secret.tool", scope=Scope.DATA_WRITE, fn=_demo_ok))
    res = reg.call("secret.tool", Role.VIEWER, 21)
    assert res.ok is False
    assert res.disclosures[0].code == "permission_denied"


def test_registry_normal_call():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="ok.tool", scope=Scope.DATA_READ, fn=_demo_ok))
    res = reg.call("ok.tool", Role.VIEWER, 21)
    assert res.ok is True
    assert res.output == 42
    assert res.meta["circuit"] == "closed"


def test_registry_unknown_tool():
    reg = ToolRegistry()
    res = reg.call("nope", Role.ADMIN)
    assert res.ok is False
    assert res.disclosures[0].code == "tool_missing"


# —— 熔断器三态 ——
def test_circuit_breaker_states():
    br = CircuitBreaker("t1", failure_threshold=3, cooldown=0.2, success_threshold=2)
    assert br.state == "closed"

    def boom():
        raise RuntimeError("x")

    # 连续 3 次失败 → open
    for _ in range(3):
        with pytest.raises(RuntimeError):
            br.call(boom)
    assert br.state == "open"

    # open 期间直接拒绝
    with pytest.raises(CircuitOpen):
        br.call(lambda: 1)

    # 冷却后 → half_open，成功 2 次 → closed
    import time

    time.sleep(0.25)
    assert br.state == "half_open"
    assert br.call(lambda: 1) == 1
    assert br.call(lambda: 1) == 1
    assert br.state == "closed"


# —— 沙箱 ——
def test_sandbox_normal():
    assert run_in_sandbox(_demo_ok, 21) == 42


def test_sandbox_timeout():
    with pytest.raises(SandboxTimeout):
        run_in_sandbox(_demo_slow, 2.0, timeout=0.4)


def test_sandbox_error_propagates():
    with pytest.raises(Exception):
        run_in_sandbox(_demo_fail)
