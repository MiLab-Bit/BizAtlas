from __future__ import annotations

"""视觉解析分支（阶段 1）。

设计目标：让商舆具备『扫描件 / 印章 / 复杂表格』的版面感知能力，
并在配置视觉后端（VLM/OCR）时做带 bbox 坐标的抽取；未配置或纯文本时
**自动降级到纯文本解析**，不影响现有 ingest 逻辑。

对标 Layra 的视觉 RAG / 多模态事实抽取——但落地策略是『框架先行、
后端可插拔』：默认零外部依赖、零副作用，需要更强能力时再接入模型。
"""

from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from bizatlas.config import get_settings


class DocumentLayoutType(str, Enum):
    TEXT = "text"  # 纯文本 PDF，可直接正则/LLM 抽取
    SCANNED = "scanned"  # 扫描件，文字层缺失，需 OCR/VLM
    SEALED = "sealed"  # 含印章/盖章，需版面/图像校验
    COMPLEX_TABLE = "complex_table"  # 复杂表格，需视觉版式解析


class VisionExtraction(BaseModel):
    """视觉后端抽取的带坐标事实。"""

    name: str
    value: float
    page: int | None = None
    bbox: str | None = None  # 版面坐标 "x,y,w,h"
    snippet: str = ""


class VisionResult(BaseModel):
    detected_type: str
    verified: bool = False  # 是否经视觉后端核验
    extractions: list[VisionExtraction] = Field(default_factory=list)
    note: str = ""


@runtime_checkable
class VisionBackend(Protocol):
    def extract(self, pdf_path: Path) -> list[VisionExtraction]:
        """从 PDF 抽取带坐标的事实；失败时抛异常由调用方降级。"""
        ...


class NullVisionBackend:
    """默认后端：不做视觉抽取（纯文本降级）。"""

    def extract(self, pdf_path: Path) -> list[VisionExtraction]:
        return []


class VLMVisionBackend:
    """VLM 视觉后端骨架（可插拔）。

    真实部署时：将 PDF 页面渲染为图像，调用多模态 LLM（配置中的
    vision_api_base / vision_api_key / vision_model）做结构化抽取，
    返回带 bbox 的 VisionExtraction。未实现时显式抛出，由 run_vision_pipeline
    捕获并降级纯文本，避免静默失效。
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.api_base = settings.vision_api_base
        self.api_key = settings.vision_api_key
        self.model = settings.vision_model

    def extract(self, pdf_path: Path) -> list[VisionExtraction]:
        raise NotImplementedError(
            "未实现：配置 vision_backend=vlm 并完成页面图像→多模态 LLM 抽取后启用。"
            "当前返回空，run_vision_pipeline 会安全降级。"
        )


def _detect_seal_text(page_texts: list[str]) -> bool:
    """无渲染的轻量印章启发：文本中出现盖章/签章标记。"""
    markers = ("盖章", "签章", "骑缝章", "公章", "鲜章")
    return any(any(m in t for m in markers) for t in page_texts)


def detect_document_type(pdf_path: Path) -> DocumentLayoutType:
    """判断 PDF 版面类型（扫描件/印章/复杂表格/纯文本）。

    纯 pypdf 文字统计 + 轻量文本标记，无需任何图像渲染库。
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:  # noqa: BLE001
        return DocumentLayoutType.TEXT

    page_texts: list[str] = []
    total = 0
    for page in reader.pages:
        t = page.extract_text() or ""
        page_texts.append(t)
        total += len(t.strip())

    # 扫描件：文字层完全缺失（图片扫描无 OCR 层），合法短文档仍按正文处理
    if total == 0:
        return DocumentLayoutType.SCANNED

    # 印章：文本标记（无需渲染）
    if _detect_seal_text(page_texts):
        return DocumentLayoutType.SEALED

    # 复杂表格：大量竖线或制表列
    for t in page_texts:
        if t.count("|") > 20 or t.count("\t") > 10:
            return DocumentLayoutType.COMPLEX_TABLE

    return DocumentLayoutType.TEXT


def get_vision_backend() -> VisionBackend:
    settings = get_settings()
    if not settings.vision_enabled:
        return NullVisionBackend()
    if settings.vision_backend == "vlm":
        return VLMVisionBackend()
    return NullVisionBackend()


def run_vision_pipeline(pdf_path: str | Path, source_ref: str) -> VisionResult:
    """视觉优先分支入口：检测版面 → 必要时视觉抽取。

    降级规则：纯文本或后端未启用 → verified=False，不阻断主流程；
    视觉后端抛异常 → 捕获并降级，note 记录原因。
    """
    pdf_path = Path(pdf_path)
    dtype = detect_document_type(pdf_path)
    backend = get_vision_backend()

    if dtype == DocumentLayoutType.TEXT or isinstance(backend, NullVisionBackend):
        return VisionResult(
            detected_type=dtype.value,
            verified=False,
            note="纯文本降级或视觉后端未启用（保留原解析）",
        )

    try:
        extras = backend.extract(pdf_path)
        return VisionResult(
            detected_type=dtype.value,
            verified=True,
            extractions=extras,
            note="视觉抽取完成（带 bbox 坐标）",
        )
    except Exception as exc:  # noqa: BLE001
        return VisionResult(
            detected_type=dtype.value,
            verified=False,
            note=f"视觉抽取失败，降级纯文本：{exc}",
        )


# ---- 多模态票据 OCR（P2）----
# 真实 VLM 调用：把发票/单据图片 base64 后发给 OpenAI 兼容 chat/completions，
# 要求模型返回结构化 JSON 票面字段。未配置视觉/LLM 时显式降级；解析失败绝不编造。
_INVOICE_PROMPT = (
    "你是票据结构化抽取器。请仔细识别这张发票/单据图片，"
    "只输出一个 JSON 对象，字段包括："
    "invoice_type(发票类型), invoice_code(发票代码), invoice_no(发票号码),"
    "date(开票日期,YYYY-MM-DD), seller_name(销售方名称), seller_tax_no(销售方税号),"
    "buyer_name(购买方名称), buyer_tax_no(购买方税号),"
    "amount(价税合计金额,number), tax(税额,number),"
    "items(明细数组,每项{name,qty,amount}), confidence(0-1,识别把握)。"
    "金额必须来自票面，不要估算；看不清的字段填 null。只输出 JSON，不要解释。"
)


def vision_ocr_available() -> bool:
    """票据 OCR 是否可用：vision 或 LLM 任一配置了 api_key + base 即可。"""
    s = get_settings()
    key = (s.vision_api_key or s.llm_api_key).strip()
    base = (s.vision_api_base or s.llm_api_base).strip()
    return bool(key and base)


def _encode_image(path: str) -> tuple[str, str]:
    import base64
    import mimetypes

    from pathlib import Path

    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return mime, data


def _extract_json(text: str):
    import json

    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        idx = t.find("```")
        if idx != -1:
            t = t[:idx]
        t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(t[s : e + 1])
            except json.JSONDecodeError:
                return None
        return None


def vision_ocr_image(file_path: str, prompt: str | None = None, timeout: float = 60.0) -> dict:
    """调用多模态 LLM 抽取发票结构化字段。

    Returns: {ok, message, fields, raw}
        - ok=False：未配置或调用/解析失败，fields=None，绝不编造票面数字。
    """
    out: dict = {"ok": False, "message": "", "fields": None, "raw": None}
    if not vision_ocr_available():
        out["message"] = "视觉后端未配置（vision_api_key 与 llm_api_key 均为空），票据 OCR 降级"
        return out
    import httpx

    try:
        s = get_settings()
        base = (s.vision_api_base or s.llm_api_base).strip().rstrip("/")
        key = (s.vision_api_key or s.llm_api_key).strip()
        model = (s.vision_model or s.llm_model).strip()
        mime, data = _encode_image(file_path)
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": prompt or _INVOICE_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": "请抽取这张发票/单据："},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
                    ]},
                ],
                "temperature": 0,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        out["raw"] = content
        fields = _extract_json(content)
        if fields is None:
            out["message"] = "VLM 未返回可解析 JSON，已保留原始文本"
            return out
        out["ok"] = True
        out["fields"] = fields
        out["message"] = "VLM 抽取成功"
        return out
    except Exception as exc:  # noqa: BLE001
        out["message"] = f"视觉后端调用失败：{exc}"
        return out
