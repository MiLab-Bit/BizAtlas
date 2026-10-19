"""BizAtlas LLM 每日配额测试 — 不调 LLM（_post_with_retry / _resolve_provider / 缓存全打桩）。

配额门位于 chat_completion 入口（_quota_gate）；BYOK（带 api_key）跳过，平台网关超限抛
LLMUnavailable（product 调用方已降级）。缓存禁用，确保每次真实走配额门。

运行（仓库根）：
    venv/bin/python -m pytest tests/test_llm_quota.py -q
"""
from __future__ import annotations

import sys

import pytest

for _p in ("/opt/bizatlas/packages", "/opt/shared"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bizatlas.llm.client as client  # noqa: E402
from bizatlas.llm.client import chat_completion, LLMUnavailable, set_llm_scope  # noqa: E402


class _Resp:
    def raise_for_status(self) -> None:
        pass

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


@pytest.fixture()
def fake_llm(monkeypatch, tmp_path):
    """真实 chat_completion + _quota_gate 执行；仅供应商 HTTP 与缓存被替换。"""
    calls: list = []

    def _fake_post(url, headers, payload, timeout=45.0):
        calls.append(payload)
        return _Resp()

    monkeypatch.setattr(client, "_post_with_retry", _fake_post)
    monkeypatch.setattr(client, "_resolve_provider", lambda p: ("http://x", "k", "m"))
    monkeypatch.setattr(client, "_cache_get", lambda k: None)
    monkeypatch.setattr(client, "_cache_put", lambda *a, **k: None)
    monkeypatch.setenv("BIZATLAS_QUOTA_DB", str(tmp_path / "q.db"))
    return calls


def test_exhausted_raises(fake_llm):
    set_llm_scope("u1")
    for _ in range(3):
        assert chat_completion([{"role": "user", "content": "hi"}]) == "ok"
    with pytest.raises(LLMUnavailable):
        chat_completion([{"role": "user", "content": "hi"}])
    assert len(fake_llm) == 3  # 第 4 次被配额门拦截，零供应商调用


def test_byok_skips_quota(fake_llm):
    set_llm_scope("u1")
    for _ in range(3):
        assert chat_completion([{"role": "user", "content": "hi"}]) == "ok"
    out = chat_completion(
        [{"role": "user", "content": "hi"}],
        provider={"api_key": "own", "base_url": "http://own", "model": "m"},
    )
    assert out == "ok"
    assert len(fake_llm) == 4  # BYOK 不计平台额度，仍放行


def test_scope_isolation(fake_llm):
    set_llm_scope("u1")
    for _ in range(3):
        assert chat_completion([{"role": "user", "content": "hi"}]) == "ok"
    set_llm_scope("u2")
    assert chat_completion([{"role": "user", "content": "hi"}]) == "ok"


def test_quota_env_unlimited(fake_llm, monkeypatch):
    monkeypatch.setenv("LLM_QUOTA_LIMIT", "0")
    set_llm_scope("u1")
    for i in range(5):
        assert chat_completion([{"role": "user", "content": f"m{i}"}]) == "ok"
    assert len(fake_llm) == 5
