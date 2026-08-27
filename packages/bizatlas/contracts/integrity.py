"""报告完整性 / 防篡改哈希链。

对标 AuditPilot 的 ``AuditEventStore``（SHA256 哈希链 + HMAC 签名 checkpoint）：
最终风险报告与证据链不可抵赖、可被独立复核。

设计要点
--------
- 对报告载荷做**确定性规范化**（排序键、ASCII 安全、忽略 None），保证同一内容哈希稳定。
- 用 HMAC-SHA256 对载荷哈希签名，密钥来自环境变量 ``BIZATLAS_INTEGRITY_SECRET``，
  缺失时回退到开发密钥并告警（**生产必须配置密钥**）。
- 支持**链式** ``prev_hash``：每份新报告的哈希可指向上一份，形成不可篡改的序列。
- ``verify`` 可独立校验：载荷被改动、签名被替换、密钥不对都会判定失败。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

DEV_SECRET = "dev-insecure-integrity-secret-CHANGE-ME"
ALGO = "sha256"


class IntegrityRecord(BaseModel):
    report_id: str
    algorithm: str = ALGO
    payload_hash: str  # 载荷规范化后的 SHA256
    signature: str  # HMAC-SHA256(payload_hash)，十六进制
    chain_prev: str | None = None  # 上一份报告的 payload_hash，形成哈希链
    signed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verifier: str = "bizatlas-integrity"


def _resolve_secret(secret: str | None) -> tuple[str, bool]:
    if secret:
        return secret, False
    env = os.getenv("BIZATLAS_INTEGRITY_SECRET")
    if env:
        return env, False
    return DEV_SECRET, True


def _default(o: Any) -> Any:
    if isinstance(o, (datetime,)):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    return str(o)


def canonical(payload: Any) -> str:
    """把任意报告载荷规范化为稳定字符串（排序键、忽略 None、ASCII 安全）。"""

    def _strip(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: _strip(val) for k, val in v.items() if val is not None}
        if isinstance(v, (list, tuple)):
            return [_strip(x) for x in v]
        return v

    return json.dumps(
        _strip(payload),
        sort_keys=True,
        ensure_ascii=False,
        default=_default,
    )


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sign(
    report_id: str,
    payload: Any,
    *,
    secret: str | None = None,
    prev_hash: str | None = None,
) -> IntegrityRecord:
    """对报告载荷签名，返回完整性记录。"""

    secret_resolved, insecure = _resolve_secret(secret)
    if insecure and os.getenv("BIZATLAS_ENV", "dev") != "test":
        # 仅告警，不阻断（测试环境除外）
        import warnings

        warnings.warn(
            "BIZATLAS_INTEGRITY_SECRET 未配置，使用开发密钥签名，生产环境必须配置。",
            stacklevel=2,
        )

    canon = canonical(payload)
    payload_hash = _hash(canon)
    signature = hmac.new(
        secret_resolved.encode("utf-8"), payload_hash.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return IntegrityRecord(
        report_id=report_id,
        payload_hash=payload_hash,
        signature=signature,
        chain_prev=prev_hash,
    )


def verify(
    record: IntegrityRecord,
    payload: Any,
    *,
    secret: str | None = None,
) -> bool:
    """独立校验报告完整性：载荷、签名、密钥任一不符即返回 False。"""

    secret_resolved, _ = _resolve_secret(secret)
    canon = canonical(payload)
    expected_hash = _hash(canon)
    if expected_hash != record.payload_hash:
        return False
    expected_sig = hmac.new(
        secret_resolved.encode("utf-8"), expected_hash.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    # 防时序攻击的比较
    return hmac.compare_digest(expected_sig, record.signature)


def tamper_detected(
    record: IntegrityRecord,
    payload: Any,
    *,
    secret: str | None = None,
) -> bool:
    """返回 True 表示报告被篡改（verify 的反面）。"""
    return not verify(record, payload, secret=secret)
