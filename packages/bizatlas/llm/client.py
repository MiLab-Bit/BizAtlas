from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

import httpx

from bizatlas.config import get_settings
from bizatlas.data.db import get_connection


class LLMUnavailable(RuntimeError):
    """LLM not configured or upstream error — callers should degrade."""


# ---- LLM 并发闸门 + 限流退避 ----
# 实测上游网关返回 `concurrent limit exceeded: running=40 max=6`，
# 超限直接抛错会让 Agent 静默降级为规则模式（接口仍返 200），
# 因此这里在客户端侧主动排队，宁可慢也不要悄悄降级。
_MAX_CONCURRENCY = max(1, int(os.getenv("LLM_MAX_CONCURRENCY", "5")))
_llm_gate = threading.BoundedSemaphore(_MAX_CONCURRENCY)
# 429 / 5xx 重试：指数退避 + jitter，尊重 Retry-After
_MAX_RETRIES = max(0, int(os.getenv("LLM_MAX_RETRIES", "3")))
_RETRY_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_BACKOFF_CAP = 20.0
# 观测计数（供 /v1/health 或日志排查用）
_gate_stats = {"acquired": 0, "waited": 0, "timeouts": 0, "retries": 0}
_gate_stats_lock = threading.Lock()


# 请求级用户自带 provider 注入：由 API 路由在请求上下文中设置，
# chat_completion 自动读取，避免把 provider 透传穿过整条调用链。
# ContextVar 随请求执行上下文隔离，天然请求安全。
_request_provider: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "bizatlas_request_provider", default=None
)
# 快路径：强制走确定性/模板降级，跳过一切 LLM 调用（贷前 demo / SSE fast）
_force_deterministic: ContextVar[bool] = ContextVar(
    "bizatlas_force_deterministic", default=False
)


def set_request_provider(provider: Optional[dict[str, Any]]) -> None:
    """设置当前请求的用户自带 provider（{api_key, base_url, model}）。"""
    _request_provider.set(provider)


def get_request_provider() -> Optional[dict[str, Any]]:
    return _request_provider.get()


def set_force_deterministic(flag: bool) -> None:
    """开启后 llm_configured() 返回 False，全链路 Agent/润色走模板降级。"""
    _force_deterministic.set(bool(flag))


def llm_configured() -> bool:
    if _force_deterministic.get():
        return False
    s = get_settings()
    return bool(s.llm_api_base.strip() and s.llm_api_key.strip())


# ---- LLM 响应缓存（chat_completion 为非流式同步调用，统一缓存） ----
# 复用 BizAtlas 应用库（get_connection）的 llm_cache 表 (cache_key PK, content, created_at, hits)。
# 缓存 key 含 provider 指纹（或平台标识），避免不同用户/key 的回答互相串。
# 验证调用走独立的 _test_provider，不经过本函数，故不影响密钥可用性验证。
_LLM_CACHE_TTL = 24 * 3600.0
_LLM_CACHE_CAP = 2000


def _cache_key(provider: dict[str, Any] | None, model: str, temperature: float,
               messages: list[dict[str, str]]) -> str:
    if provider:
        pid = provider.get("id") or (
            "key:" + hashlib.sha256((provider.get("api_key") or "").encode()).hexdigest()[:16]
        )
    else:
        pid = "platform"
    payload = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    raw = f"{pid}|{model}|{temperature}|{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache ("
                "cache_key TEXT PRIMARY KEY, content TEXT NOT NULL, "
                "created_at REAL NOT NULL, hits INT NOT NULL DEFAULT 0)"
            )
            row = conn.execute(
                "SELECT content, created_at FROM llm_cache WHERE cache_key=?", (key,)
            ).fetchone()
            if not row:
                return None
            if time.time() - row["created_at"] > _LLM_CACHE_TTL:
                conn.execute("DELETE FROM llm_cache WHERE cache_key=?", (key,))
                conn.commit()
                return None
            conn.execute("UPDATE llm_cache SET hits=hits+1 WHERE cache_key=?", (key,))
            conn.commit()
            return row["content"]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — 缓存异常不影响主流程
        return None


def _cache_put(key: str, content: str) -> None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache ("
                "cache_key TEXT PRIMARY KEY, content TEXT NOT NULL, "
                "created_at REAL NOT NULL, hits INT NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "INSERT INTO llm_cache (cache_key, content, created_at, hits) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(cache_key) DO UPDATE SET content=excluded.content, "
                "created_at=excluded.created_at, hits=excluded.hits",
                (key, content, time.time()),
            )
            n = conn.execute("SELECT COUNT(*) AS n FROM llm_cache").fetchone()["n"]
            if n > _LLM_CACHE_CAP:
                excess = n - _LLM_CACHE_CAP
                old = conn.execute(
                    "SELECT cache_key FROM llm_cache ORDER BY created_at ASC LIMIT ?", (excess,)
                ).fetchall()
                for r in old:
                    conn.execute("DELETE FROM llm_cache WHERE cache_key=?", (r["cache_key"],))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def _extract_content(data: Any) -> str:
    try:
        message = data["choices"][0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailable(f"unexpected LLM response: {data!r}") from exc
    if not isinstance(content, str) or not content.strip():
        # 推理型模型（如 GLM-5.2）会把 token 消耗在 reasoning_content 上，
        # max_tokens 给小时 content 直接为空。这里把原因写进异常，避免线上只能看到「降级」。
        reasoning = ""
        finish = ""
        try:
            reasoning = str(message.get("reasoning_content") or "")
        except AttributeError:
            reasoning = ""
        try:
            finish = str(data["choices"][0].get("finish_reason") or "")
        except (KeyError, IndexError, AttributeError, TypeError):
            finish = ""
        detail = f"finish_reason={finish or 'unknown'}"
        if reasoning.strip():
            raise LLMUnavailable(
                f"empty LLM content：模型把 token 消耗在推理上（reasoning {len(reasoning)} 字符），"
                f"需提高 max_tokens；{detail}"
            )
        raise LLMUnavailable(f"empty LLM content；{detail}")
    return content.strip()


def _chat_via_curl(
    url: str,
    key: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> str:
    """Windows 上 httpx 偶发 SSL EOF，走系统 curl 更稳。"""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise LLMUnavailable("curl unavailable")
    with tempfile.TemporaryDirectory() as td:
        body_path = Path(td) / "payload.json"
        body_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [
                curl,
                "-sS",
                "-X",
                "POST",
                url,
                "--noproxy",
                "*",  # 同上：绕过本机代理，直连网关
                "-H",
                f"Authorization: Bearer {key}",
                "-H",
                "Content-Type: application/json",
                "--data-binary",
                f"@{body_path}",
                "--max-time",
                str(int(timeout)),
            ],
            capture_output=True,
            timeout=timeout + 5,
            check=False,
        )
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise LLMUnavailable(err or f"curl exit {proc.returncode}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"LLM non-JSON: {out[:200]}") from exc
    return _extract_content(data)


def _iter_sse_lines(text_iter: Any) -> Any:
    """从 OpenAI 兼容的 SSE 文本流里逐条 yield `data:` 负载（JSON 字符串）。"""
    buf = ""
    for chunk in text_iter:
        if chunk:
            buf += chunk
        while "\n\n" in buf:
            event, buf = buf.split("\n\n", 1)
            for line in event.split("\n"):
                line = line.strip()
                if line.startswith("data:"):
                    payload = line[len("data:"):].strip()
                    if payload and payload != "[DONE]":
                        yield payload


def _replay_chunks(content: str, size: int = 4) -> Any:
    """把缓存的完整回答切成小段重放，模拟流式输出。"""
    for i in range(0, len(content), size):
        yield content[i : i + size]


def _chat_via_curl_stream(
    url: str,
    key: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    """curl 流式回退：`-N` 关缓冲，逐行解析 SSE。"""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise LLMUnavailable("curl unavailable")
    with tempfile.TemporaryDirectory() as td:
        body_path = Path(td) / "payload.json"
        body_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.Popen(
            [
                curl,
                "-sS",
                "-N",
                "-X",
                "POST",
                url,
                "--noproxy",
                "*",
                "-H",
                f"Authorization: Bearer {key}",
                "-H",
                "Content-Type: application/json",
                "-H",
                "Accept: text/event-stream",
                "--data-binary",
                f"@{body_path}",
                "--max-time",
                str(int(timeout)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            for line in _iter_sse_lines(proc.stdout):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = data["choices"][0]["delta"]["content"]
                except (KeyError, IndexError, TypeError):
                    continue
                if delta:
                    yield delta
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.wait(timeout=5)


def gate_stats() -> dict[str, int]:
    """返回并发闸门的观测计数（排队次数、重试次数、等待超时次数）。"""
    with _gate_stats_lock:
        return dict(_gate_stats)


def _backoff_delay(resp: Any, attempt: int) -> float:
    """指数退避 + jitter；上游给了 Retry-After 时以其为准。"""
    retry_after = None
    if resp is not None:
        raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
        if raw:
            try:
                retry_after = float(str(raw).strip())
            except ValueError:
                retry_after = None
    if retry_after is not None and retry_after >= 0:
        return min(retry_after, _BACKOFF_CAP)
    return min(1.5 * (2 ** attempt) + random.uniform(0.0, 0.6), _BACKOFF_CAP)


def _acquire_gate(timeout: float) -> None:
    """获取并发闸门；超时说明上游被压满，抛 LLMUnavailable 让调用方显式降级。"""
    got = _llm_gate.acquire(timeout=max(timeout, 1.0))
    with _gate_stats_lock:
        if got:
            _gate_stats["acquired"] += 1
        else:
            _gate_stats["timeouts"] += 1
    if not got:
        raise LLMUnavailable(
            f"LLM 并发闸门等待超时（{timeout:.0f}s，上限 {_MAX_CONCURRENCY}），上游可能已被压满"
        )


def _post_with_retry(url: str, headers: dict[str, str], payload: dict[str, Any],
                     timeout: float) -> Any:
    """带并发闸门 + 429/5xx 指数退避的 chat/completions 请求。

    只重试「可恢复」的错误：连接超时、429、5xx。4xx（除 429/408/425）不重试。
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        _acquire_gate(timeout)
        try:
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                with _gate_stats_lock:
                    _gate_stats["retries"] += 1
                delay = _backoff_delay(resp, attempt)
                time.sleep(delay)
                continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError,
                httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt >= _MAX_RETRIES:
                raise
            with _gate_stats_lock:
                _gate_stats["retries"] += 1
            time.sleep(_backoff_delay(None, attempt))
        finally:
            _llm_gate.release()
    raise LLMUnavailable(str(last_exc) if last_exc else "LLM 请求失败（重试耗尽）")


def _resolve_provider(provider: dict[str, Any] | None):
    """返回 (base, key, model)；provider 为 None 时回退到请求级注入 / 平台设置。"""
    if provider is None:
        provider = get_request_provider()
    if provider:
        base = (provider.get("base_url") or "").rstrip("/")
        key = (provider.get("api_key") or "").strip()
        model = (provider.get("model") or "").strip() or "Qwen-flash"
    else:
        s = get_settings()
        base = s.llm_api_base.rstrip("/")
        key = s.llm_api_key.strip()
        model = s.llm_model.strip() or "Qwen-flash"
    if not base or not key:
        raise LLMUnavailable("LLM base_url / api_key not set")
    return base, key, model


def _chat_completion_sync(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
    provider: dict[str, Any] | None,
) -> str:
    """非流式：返回完整 str（与历史行为一致）。命中缓存即返回，不触发供应商。"""
    base, key, model = _resolve_provider(provider)
    cache_key = _cache_key(provider, model, temperature, messages)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        resp = _post_with_retry(url, headers, payload, timeout=timeout)
        resp.raise_for_status()
        content = _extract_content(resp.json())
    except LLMUnavailable:
        raise
    except Exception as httpx_exc:  # noqa: BLE001 — degrade / curl fallback
        try:
            content = _chat_via_curl(url, key, payload, timeout=timeout)
        except Exception as curl_exc:  # noqa: BLE001
            raise LLMUnavailable(str(curl_exc) or str(httpx_exc)) from curl_exc
    _cache_put(cache_key, content)
    return content


def _chat_completion_stream(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
    provider: dict[str, Any] | None,
):
    """流式生成器：逐段 yield 文本 chunk。

    命中缓存时把完整回答切成小段重放（流式缓存）；未命中时边调供应商边 yield，
    并在结束时写缓存。
    """
    base, key, model = _resolve_provider(provider)
    cache_key = _cache_key(provider, model, temperature, messages)
    cached = _cache_get(cache_key)
    if cached is not None:
        yield from _replay_chunks(cached)
        return
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    parts: list[str] = []
    # 流式同样走并发闸门：SSE 长连接会长时间占用上游额度，不放闸比非流式更容易打爆
    _acquire_gate(timeout)
    try:
        try:
            with httpx.Client(timeout=timeout, trust_env=False).stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                for line in _iter_sse_lines(resp.iter_text()):
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = data["choices"][0]["delta"]["content"]
                    except (KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        parts.append(delta)
                        yield delta
        except Exception as httpx_exc:  # noqa: BLE001 — degrade / curl fallback
            try:
                for delta in _chat_via_curl_stream(url, key, payload, timeout=timeout):
                    parts.append(delta)
                    yield delta
            except Exception as curl_exc:  # noqa: BLE001
                raise LLMUnavailable(str(curl_exc) or str(httpx_exc)) from curl_exc
    finally:
        _llm_gate.release()
    _cache_put(cache_key, "".join(parts))


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

    stream=False（默认）: 返回完整 str，与历史行为完全一致（5 个既有调用方不受影响）。
    stream=True: 返回一个生成器，逐段 yield 文本 chunk（含流式缓存重放）。
    """
    if stream:
        return _chat_completion_stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            provider=provider,
        )
    return _chat_completion_sync(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        provider=provider,
    )
