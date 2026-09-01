"""票据/单证 OCR 数据源（P2 多模态票据 OCR，接 ingest.vision 视觉后端）。

- 配置视觉后端（或复用 LLM）后，extract_invoice 实调用 VLM 抽取票面字段。
- 未配置时显式降级（ok=False + 原因），绝不抛异常、绝不编造数字。
"""
from __future__ import annotations

from typing import Any

from bizatlas.ingest.vision import vision_ocr_available, vision_ocr_image


def invoice_ocr_configured() -> bool:
    """票据 OCR 是否可用（vision/LLM 任一配置了 key+base）。"""
    return vision_ocr_available()


def extract_invoice(file_path: str) -> dict[str, Any]:
    """从发票/单据图片抽取结构化字段。

    Returns:
        {source, file, ok, message, fields}
        - ok=False：降级/未配置/调用失败。fields=None。绝不编造票面数字。
    """
    out: dict[str, Any] = {
        "source": "invoice_ocr",
        "file": file_path,
        "ok": False,
        "message": "",
        "fields": None,
    }
    if not invoice_ocr_configured():
        out["message"] = "视觉后端未配置（vision_api_key 与 llm_api_key 均为空），票据 OCR 降级跳过"
        return out
    try:
        fields = _extract_real(file_path)
        out["ok"] = True
        out["fields"] = fields
        out["message"] = "票据 OCR 实调用成功"
    except Exception as exc:  # noqa: BLE001
        out["message"] = f"票据 OCR 实调用失败：{exc}"
    return out


def _extract_real(file_path: str) -> dict[str, Any]:
    """实调用：委托视觉后端做 VLM 结构化抽取，返回票面字段。"""
    res = vision_ocr_image(file_path)
    if not res["ok"]:
        raise RuntimeError(res["message"])
    return res["fields"]
