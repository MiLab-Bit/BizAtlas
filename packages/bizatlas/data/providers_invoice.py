"""票据/单证 OCR 数据源（P2 多模态票据 OCR 占位 + 优雅降级）。

接口契约：声明「发票/单据结构化抽取」标准返回。依赖视觉后端
（vision_enabled + vision_backend）做多模态 OCR；未配置时显式降级。

接入具体 OCR/VLM 时，在 :func:`_extract_real` 内填充实调用。
"""
from __future__ import annotations

from typing import Any

from bizatlas.config import get_settings


def invoice_ocr_configured() -> bool:
    """是否配置了视觉后端（多模态票据 OCR 前置）。"""
    s = get_settings()
    return bool(getattr(s, "vision_enabled", False)) and bool(
        getattr(s, "vision_api_key", "").strip()
    )


def extract_invoice(file_path: str) -> dict[str, Any]:
    """从发票/单据图片抽取结构化字段。

    Returns:
        {source, file, ok, message, fields}
        - ok=False：降级/未配置。fields=None。绝不编造票面数字。
    """
    out: dict[str, Any] = {
        "source": "invoice_ocr",
        "file": file_path,
        "ok": False,
        "message": "",
        "fields": None,
    }
    if not invoice_ocr_configured():
        out["message"] = "视觉后端未启用（vision_enabled=false 或 vision_api_key 为空），票据 OCR 降级跳过"
        return out
    # TODO: 接入具体 OCR/VLM（保留 _extract_real 钩子）
    out["message"] = "票据 OCR 已配置视觉后端但实调用未实现（待接入具体模型）"
    return out


def _extract_real(file_path: str) -> dict[str, Any]:
    """实调用钩子：接入具体 OCR/VLM 时实现。返回票面字段（金额/税号/日期…）。"""
    raise NotImplementedError("票据 OCR 实调用待接入具体视觉模型")
