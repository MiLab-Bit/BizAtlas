"""企业鉴权 RBAC（阶段 3）测试。"""

from __future__ import annotations

import pytest

from bizatlas.auth.rbac import (
    Action,
    PermissionDenied,
    Principal,
    TokenInvalid,
    anonymous_admin,
    authorize,
    issue_token,
    require_permission,
    verify_token,
)
from bizatlas.tools.permissions import Role


def test_authorize_matrix():
    assert authorize(Role.VIEWER, Action.ANALYZE)
    assert not authorize(Role.VIEWER, Action.EXPORT_REPORTS)
    assert authorize(Role.ANALYST, Action.EXPORT_REPORTS)
    assert authorize(Role.REVIEWER, Action.REVIEW_APPROVE)
    assert authorize(Role.ADMIN, Action.ADMIN)


def test_require_permission_raises():
    with pytest.raises(PermissionDenied):
        require_permission(Role.VIEWER, Action.EXPORT_REPORTS)


def test_anonymous_admin_has_all():
    p = anonymous_admin()
    assert p.role == Role.ADMIN
    for a in Action:
        assert p.can(a)


def test_token_roundtrip():
    secret = "strong-secret"
    tok = issue_token("alice", Role.REVIEWER, secret)
    p = verify_token(tok, secret)
    assert isinstance(p, Principal)
    assert p.user_id == "alice"
    assert p.role == Role.REVIEWER
    assert p.can(Action.REVIEW_APPROVE)


def test_token_bad_signature():
    secret = "strong-secret"
    tok = issue_token("alice", Role.REVIEWER, secret)
    with pytest.raises(TokenInvalid):
        verify_token(tok + "x", secret)


def test_token_expired():
    secret = "strong-secret"
    # ttl=-1 → exp 落入过去，立即过期
    tok = issue_token("alice", Role.REVIEWER, secret, ttl=-1)
    with pytest.raises(TokenInvalid):
        verify_token(tok, secret)
