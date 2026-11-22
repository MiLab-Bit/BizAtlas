"""Regression checks for the isolated canonical digest candidate."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bizatlas.dq.canonical_digest import canonical_bytes, content_digest


def test_dict_order_does_not_change_digest():
    assert content_digest({"b": 2, "a": 1}) == content_digest({"a": 1, "b": 2})


def test_decimal_preserves_type_and_normalizes_zero():
    assert canonical_bytes(Decimal("1.200")) == canonical_bytes(Decimal("1.2"))
    assert canonical_bytes(Decimal("-0.000")) == canonical_bytes(Decimal("0"))
    assert canonical_bytes(Decimal("1")) != canonical_bytes("1")


def test_missing_differs_from_explicit_zero():
    assert content_digest({"x": None}) != content_digest({"x": 0})


def test_unsupported_float_fails_closed():
    with pytest.raises(TypeError):
        content_digest({"risk": 0.1})


def test_datetime_is_explicit():
    stamp = datetime(2026, 11, 22, tzinfo=timezone.utc)
    assert b"$temporal" in canonical_bytes(stamp)
