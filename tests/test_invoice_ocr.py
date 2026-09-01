from __future__ import annotations

from unittest.mock import patch

from bizatlas.data import providers_invoice


def test_invoice_ocr_degrade_when_unconfigured():
    with patch.object(providers_invoice, "vision_ocr_available", return_value=False):
        res = providers_invoice.extract_invoice("/tmp/fake-invoice.png")
    assert res["ok"] is False
    assert res["fields"] is None
    assert "降级" in res["message"]


def test_invoice_ocr_real_call_parses_fields():
    fake = {"ok": True, "fields": {"invoice_no": "X123", "amount": 100.0}, "raw": "{}", "message": "ok"}
    with patch.object(providers_invoice, "vision_ocr_available", return_value=True), \
         patch.object(providers_invoice, "vision_ocr_image", return_value=fake):
        res = providers_invoice.extract_invoice("/tmp/invoice.png")
    assert res["ok"] is True
    assert res["fields"]["invoice_no"] == "X123"
    assert res["fields"]["amount"] == 100.0


def test_invoice_ocr_real_call_failure_degrades():
    fake = {"ok": False, "fields": None, "raw": None, "message": "VLM 未返回可解析 JSON"}
    with patch.object(providers_invoice, "vision_ocr_available", return_value=True), \
         patch.object(providers_invoice, "vision_ocr_image", return_value=fake):
        res = providers_invoice.extract_invoice("/tmp/invoice.png")
    assert res["ok"] is False


def test_extract_json_strips_code_fences():
    from bizatlas.ingest.vision import _extract_json

    assert _extract_json("```json\n{\"a\":1}\n```") == {"a": 1}
    assert _extract_json("前情 {\"b\":2} 后语") == {"b": 2}
    assert _extract_json("not json") is None
