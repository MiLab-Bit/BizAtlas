"""工具治理的权限基元：角色（Role）与权限域（Scope）。

这是 BizAtlas 治理层的「单一事实源」：工具治理（tools/）与企业鉴权（auth/rbac）
共用同一套 Role/Scope 定义，避免两套权限模型漂移。

设计原则（对齐商舆内核的确定性）：
- 最小权限：每个角色只拿到完成职责所需的 Scope。
- Scope 是权限原子；RBAC 的 Action 只是 Scope 的语义别名（见 auth/rbac.py）。
- 治理在调用前做硬校验，拒绝即返回显式披露，绝不静默放行。
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class Scope(str, Enum):
    """权限域（权限原子）。"""

    DATA_READ = "data:read"          # 读取企业/指标/资料
    DATA_WRITE = "data:write"        # 写入企业/指标/上传资料
    TOOL_CALL = "tool:call"          # 调用外部/重工具（数据源拉取等）
    REVIEW_APPROVE = "review:approve"  # 通过人工复核
    REVIEW_REJECT = "review:reject"    # 驳回/退回人工复核
    MANAGE_RULES = "rules:manage"    # 规则编译/激活
    MANAGE_COMPANIES = "companies:manage"  # 企业管理类操作
    EXPORT_REPORTS = "reports:export"  # 落盘导出报告
    ADMIN = "admin"                  # 全部权限（仅 ADMIN 持有）


class Role(str, Enum):
    """企业角色（最小权限分级）。"""

    VIEWER = "viewer"      # 只读观察者
    ANALYST = "analyst"    # 分析师：可上传/研判/导出
    REVIEWER = "reviewer"  # 复核员：可审批高风险结论
    ADMIN = "admin"        # 管理员：全部权限


# 角色 → 拥有的权限域集合（最小权限矩阵）
ROLE_SCOPES: dict[Role, set[Scope]] = {
    Role.VIEWER: {Scope.DATA_READ},
    Role.ANALYST: {
        Scope.DATA_READ,
        Scope.DATA_WRITE,
        Scope.TOOL_CALL,
        Scope.EXPORT_REPORTS,
    },
    Role.REVIEWER: {Scope.DATA_READ, Scope.REVIEW_APPROVE, Scope.REVIEW_REJECT},
    Role.ADMIN: set(Scope),  # 全部
}


class AccessDenied(Exception):
    """角色缺少所需 Scope 时抛出（治理层会转译为显式披露）。"""

    def __init__(self, role: Role, scope: Scope) -> None:
        self.role = role
        self.scope = scope
        super().__init__(f"role {role.value} 缺少权限域 {scope.value}")


def role_has_scope(role: Role, scope: Scope) -> bool:
    """角色是否持有某权限域。"""
    return scope in ROLE_SCOPES.get(role, set())


def require_scope(role: Role, scope: Scope) -> None:
    """调用前硬校验；不满足抛 AccessDenied。"""
    if not role_has_scope(role, scope):
        raise AccessDenied(role, scope)


def scopes_of(role: Role) -> set[Scope]:
    """返回角色的全部权限域（用于令牌签发/审计展示）。"""
    return set(ROLE_SCOPES.get(role, set()))


def all_roles() -> list[Role]:
    return [r for r in Role]


def all_scopes() -> list[Scope]:
    return [s for s in Scope]


def matrix_summary() -> list[dict[str, str | bool]]:
    """权限矩阵的人类可读快照（供 /admin 端点与管理审计）。"""
    rows: list[dict[str, str | bool]] = []
    for role in Role:
        row: dict[str, str | bool] = {"role": role.value}
        for scope in Scope:
            row[scope.value] = scope in ROLE_SCOPES[role]
        rows.append(row)
    return rows
