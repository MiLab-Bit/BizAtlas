"""BizAtlas 限速与客户端 IP 解析（apps/api）。

- get_client_ip: 还原真实客户端 IP（穿透 Cloudflare / nginx 隧道 / 反代）。
  优先级：CF-Connecting-IP → X-Forwarded-For 首个 → X-Real-IP → client.host 兜底。
- 内存滑动窗口限速：单机够用；多实例部署可换 Redis 等共享后端。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# 默认限速策略：(最大次数, 时间窗秒)
LOGIN_LIMIT = (10, 60)          # 登录 10 次/分/IP
REGISTER_LIMIT = (5, 60)        # 注册 5 次/分/IP
PW_RESET_LIMIT = (5, 3600)      # 密码重置 5 次/时/邮箱
RESET_PW_LIMIT = (10, 60)       # 用 token 重置密码 10 次/分/IP（防 token 爆破）

_buckets: dict[str, deque[float]] = defaultdict(deque)


def get_client_ip(request: Request) -> str | None:
    """还原真实客户端 IP（P1-5）。"""
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    xrip = request.headers.get("X-Real-IP")
    if xrip:
        return xrip.strip()
    return request.client.host if request.client else None


def _sweep(dq: deque[float], window: int, now: float) -> None:
    while dq and dq[0] <= now - window:
        dq.popleft()


def rate_limit(key: str, limit: int, window: int) -> None:
    """滑动窗口限速；超限抛 429。"""
    now = time.time()
    dq = _buckets[key]
    _sweep(dq, window, now)
    if len(dq) >= limit:
        retry = int(dq[0] + window - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"too many requests, retry after {retry}s",
        )
    dq.append(now)


def rate_limit_ip(request: Request, scope: str, limit: int, window: int) -> None:
    ip = get_client_ip(request) or "unknown"
    rate_limit(f"{scope}:{ip}", limit, window)


def rate_limit_identity(identifier: str, scope: str, limit: int, window: int) -> None:
    rate_limit(f"{scope}:{identifier}", limit, window)
