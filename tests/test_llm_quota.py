"""BizAtlas LLM 每日配额测试 — 不调 LLM（打桩 Gateway 客户端）。

bizatlas.llm.client 现已委托 openclaw_core.gateway.Gateway；本测试只替换 Gateway 的
客户端构造与配额/缓存存储，验证 chat_completion 这一层的配额门、BYOK 跳过、
缓存命中不计量行为（真实网关逻辑在 openclaw_core 黄金测试中覆盖）。

运行（仓库根）：venv/bin/python -m pytest tests/test_llm_quota.py -q
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

for _p in ("/opt/bizatlas/packages", "/opt/shared"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bizatlas.llm.client as client  # noqa: E402
from bizatlas.llm.client import (  # noqa: E402
    LLMUnavailable,
    chat_completion,
    set_llm_scope,
)
from openclaw_core.gateway import _SqliteCache  # noqa: E402
from openclaw_core.quota import QuotaGate  # noqa: E402


class _Resp:
    def __init__(self):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content="ok"))]


class _Completions:
    def __init__(self, fc):
        self.fc = fc

    async def create(self, **kw):
        self.fc.calls.append(kw)
        return _Resp()


class _Chat:
    def __init__(self, fc):
        self.completions = _Completions(fc)


class _FakeClient:
    def __init__(self):
        self.calls: list = []
        self.chat = _Chat(self)


@pytest.fixture()
def fake_llm(monkeypatch, tmp_path):
    """真实 chat_completion 执行；仅 Gateway 的客户端构造与配额/缓存被替换。"""
    qdb = str(tmp_path / "q.db")
    cdb = str(tmp_path / "c.db")
    gate = QuotaGate(qdb, limit=3)
    client._gateway._quota = gate
    client._gateway._cache = _SqliteCache(cdb, 86400, 2000)
    fc = _FakeClient()
    monkeypatch.setattr(client._gateway, "_client", lambda b, k: fc)
    # 保证 _resolve 总能拿到平台网关地址（测试环境未必配置了真实 key）
    monkeypatch.setenv("LLM_API_BASE", "http://fake-gateway")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("BIZATLAS_QUOTA_DB", qdb)
    return fc, gate


def _call(content: str = "hi", **kw):
    return chat_completion([{"role": "user", "content": content}], **kw)


def test_exhausted_raises(fake_llm):
    set_llm_scope("u1")
    for i in range(3):
        assert _call(content=f"m{i}") == "ok"  # 3 次不同消息，各自计量
    with pytest.raises(LLMUnavailable):
        _call(content="exhaust")  # 第 4 次超默认 3 → 配额门拦截
    assert len(fake_llm[0].calls) == 3  # 第 4 次未触达客户端


def test_byok_skips_quota(fake_llm):
    set_llm_scope("u1")
    for i in range(3):
        assert _call(content=f"m{i}") == "ok"
    out = _call(
        content="byok",
        provider={"api_key": "own", "base_url": "http://own", "model": "m"},
    )
    assert out == "ok"
    assert len(fake_llm[0].calls) == 4  # BYOK 不计平台额度，仍放行


def test_scope_isolation(fake_llm):
    set_llm_scope("u1")
    for i in range(3):
        assert _call(content=f"u1-{i}") == "ok"  # u1 耗尽
    set_llm_scope("u2")
    assert _call(content="u2-1") == "ok"  # 不同 scope 独立配额


def test_quota_env_unlimited(fake_llm, monkeypatch, tmp_path):
    client._gateway._quota = QuotaGate(str(tmp_path / "unlim.db"), limit=None)
    set_llm_scope("u1")
    for i in range(5):
        assert _call(content=f"m{i}") == "ok"
    assert len(fake_llm[0].calls) == 5


def test_cache_hit_does_not_consume_quota(fake_llm):
    set_llm_scope("u1")
    assert _call(content="same") == "ok"  # 缓存未命中 → 计量 + 调用 + 写入缓存
    assert _call(content="same") == "ok"  # 缓存命中 → 免费返回
    assert len(fake_llm[0].calls) == 1
    assert fake_llm[1].used("u1") == 1  # 缓存命中不计量
