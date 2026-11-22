"""Deterministic, loss-aware content digests for data-quality records.

Adapted from Ark task 37699 / frore 90667 hashing.py.
This module is intentionally standalone; no pipeline integration is implied.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite Decimal cannot be hashed")
        if value.is_zero():
            return {"$decimal": "0"}
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return {"$decimal": text}
    if isinstance(value, (datetime, date)):
        return {"$temporal": value.isoformat()}
    if isinstance(value, bytes):
        return {"$bytes_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        raise TypeError("Use Decimal for exact numeric data")
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("Object keys must be strings")
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    raise TypeError(f"Unsupported value type: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
