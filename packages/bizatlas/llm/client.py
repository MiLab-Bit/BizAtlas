"""bizatlas.llm.client — 委托 openclaw_core.gateway.Gateway。

配额门控 / 并发闸门 / 指数退避 / 响应缓存 / provider 解析 / JSON 兜底
全部下沉到共享库 openclaw_core；本文件只保留产品级对外符号：

  chat_completion, LLMUnavailable, llm_configured,
  set_request_provider, get_request_provider, set_llm_scope,
  set_force_deterministic, gate_stats

调用点零改动。LLMUnavailable 与 openclaw_core 的同类异常保持同一身份，
因此调用方 `except LLMUnavailable` 仍能捕获平台/网关/配额/上游各类软失败。
"""
from __future__ import annotations

import asyncio
import os
from contextvars import ContextVar
from typing import Any, Iterator, Optional

from openclaw_core.gateway import Gateway, QuotaExceeded, LLMUnavailable

from bizatlas.config import get_settings


__all__ = [
    "LLMUnavailable",
    "chat_completion",
    "llm_configured",
    "set_request_provider",
    "get_request_provider",
    "set_llm_scope",
    "set_force_deterministic",
    "gate_stats",
]


# ---- 请求级上下文（与历史完全一致，由 API 路由在请求生命周期内设置）----
# provider 透传穿过整条调用链的工作由 ContextVar 承担，天然请求安全。
_request_provider: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "bizatlas_request_provider", default=None
)
# 快路径：强制走确定性/模板降级，跳过一切 LLM 调用（贷前 demo / SSE fast）。
_force_deterministic: ContextVar[bool] = ContextVar(
    "bizatlas_force_deterministic", default=False
)
# 平台网关每日配额 scope（用户 id）；BYOK 不计。
_llm_scope: ContextVar[str] = ContextVar("bizatlas_llm_scope", default="anon")


def set_request_provider(provider: Optional[dict[str, Any]]) -> None:
    """设置当前请求的用户自带 provider（{api_key, base_url, model}）。"""
    _request_provider.set(provider)


def get_request_provider() -> Optional[dict[str, Any]]:
    return _request_provider.get()


def set_llm_scope(scope: str) -> None:
    """设置当前请求的配额 scope（用户 id）；随请求 ContextVar 隔离。"""
    _llm_scope.set(scope or "anon")


def set_force_deterministic(flag: bool) -> None:
    """开启后 llm_configured() 返回 False，全链路 Agent/润色走模板降级。"""
    _force_deterministic.set(bool(flag))


def llm_configured() -> bool:
    if _force_deterministic.get():
        return False
    s = get_settings()
    return bool(s.llm_api_base.strip() and s.llm_api_key.strip())


def _quota_db_path() -> str:
    return os.getenv("BIZATLAS_QUOTA_DB") or os.path.join(
        os.path.dirname(get_settings().bizatlas_db_path), "llm_quota.db"
    )


# 统一网关：并发闸门 / 退避 / 缓存 / 配额 / provider 解析一套实现，跨产品复用。
# 配置与历史 client.py 对齐：并发 5、重试 3、缓存 24h/2000 条、配额库沿用 llm_quota.db。
_gateway = Gateway(
    platform_base_url=get_settings().llm_api_base or None,
    platform_api_key=get_settings().llm_api_key or None,
    default_model=get_settings().llm_model or "Qwen-flash",
    base_url_env="LLM_API_BASE",
    key_env="LLM_API_KEY",
    model_env="LLM_MODEL",
    quota_db=_quota_db_path(),
    max_concurrency=max(1, int(os.getenv("LLM_MAX_CONCURRENCY", "5"))),
    max_retries=max(0, int(os.getenv("LLM_MAX_RETRIES", "3"))),
    timeout=float(os.getenv("LLM_TIMEOUT", "180")),
    cache_db=os.getenv("BIZATLAS_LLM_CACHE_DB")
    or _quota_db_path().replace("llm_quota.db", "llm_cache.db"),
    cache_ttl=24 * 3600.0,
    cache_cap=2000,
)


def _raise_quota_as_unavailable(exc: QuotaExceeded) -> None:
    """平台网关配额超限：历史语义是抛 LLMUnavailable 让调用方降级，保持之。"""
    raise LLMUnavailable("daily LLM quota exhausted") from exc


def _empty_to_unavailable(content: str) -> str:
    """推理型模型（GLM-5.2 等）常把 token 消耗在 reasoning 上导致正文为空；
    与历史行为一致：空正文视为软失败，交由调用方降级，而非返回空串。"""
    if not content or not content.strip():
        raise LLMUnavailable("empty LLM content")
    return content


def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    timeout: float = 45.0,
    provider: dict[str, Any] | None = None,
    stream: bool = False,
) -> Any:
    """OpenAI-compatible chat completions. Raises LLMUnavailable on soft failure.

    provider: 可选 {api_key, base_url, model}，用户自带凭证，优先于平台设置。
    未显式传入时回退到请求级注入的 provider（set_request_provider）。

    stream=False（默认）: 返回完整 str，与历史行为完全一致（既有调用方不受影响）。
    stream=True: 返回一个同步生成器，逐段 yield 文本 chunk。
    """
    eff_provider = provider or get_request_provider()
    scope = _llm_scope.get()
    if stream:
        return _chat_completion_stream_sync(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=eff_provider,
            scope=scope,
        )
    try:
        content = _gateway.chat_sync(
            messages,
            model=None,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            provider=eff_provider,
            scope=scope,
        )
    except QuotaExceeded as exc:
        _raise_quota_as_unavailable(exc)
    return _empty_to_unavailable(content)


def _chat_completion_stream_sync(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    provider: dict[str, Any] | None,
    scope: str,
) -> Iterator[str]:
    """把 Gateway 的异步流式迭代器适配成同步生成器（独立事件循环，线程安全）。"""
    loop = asyncio.new_event_loop()
    try:
        try:
            async_gen = loop.run_until_complete(
                _gateway.chat(
                    messages,
                    model=None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    provider=provider,
                    scope=scope,
                )
            )
        except QuotaExceeded as exc:
            _raise_quota_as_unavailable(exc)
        while True:
            try:
                chunk = loop.run_until_complete(async_gen.__anext__())
            except StopAsyncIteration:
                break
            if chunk:
                yield chunk
    finally:
        loop.close()


def gate_stats() -> dict[str, int]:
    """并发闸门观测计数（兼容性保留；统一网关后由 openclaw_core 内部统计）。"""
    return {"acquired": 0, "waited": 0, "timeouts": 0, "retries": 0}
