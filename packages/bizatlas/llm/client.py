from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from bizatlas.config import get_settings


class LLMUnavailable(RuntimeError):
    """LLM not configured or upstream error — callers should degrade."""


def llm_configured() -> bool:
    s = get_settings()
    return bool(s.llm_api_base.strip() and s.llm_api_key.strip())


def _extract_content(data: Any) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailable(f"unexpected LLM response: {data!r}") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMUnavailable("empty LLM content")
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


def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 800,
    timeout: float = 45.0,
) -> str:
    """OpenAI-compatible chat completions. Raises LLMUnavailable on soft failure."""
    s = get_settings()
    base = s.llm_api_base.rstrip("/")
    key = s.llm_api_key.strip()
    model = s.llm_model.strip() or "Qwen-flash"
    if not base or not key:
        raise LLMUnavailable("LLM_API_BASE / LLM_API_KEY not set")

    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        # trust_env=False：绕过本机 Clash 等代理（HTTPS_PROXY/HTTP_PROXY），
        # 直连用户自建网关 www.abc-ai.cn（直连 0.2s，走代理会超时）。
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return _extract_content(resp.json())
    except Exception as httpx_exc:  # noqa: BLE001 — degrade / curl fallback
        try:
            return _chat_via_curl(url, key, payload, timeout=timeout)
        except Exception as curl_exc:  # noqa: BLE001
            raise LLMUnavailable(str(curl_exc) or str(httpx_exc)) from curl_exc
