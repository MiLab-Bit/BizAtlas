from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from bizatlas.contracts.models import DataTier, Evidence, MetricSource, MetricValue

# 名称 → 匹配模式（取第一个数值；支持 12.3% / 0.123 / 12.3）
METRIC_PATTERNS: list[tuple[str, str, str]] = [
    ("流动比率", r"流动比率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("速动比率", r"速动比率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("资产负债率", r"资产负债率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("利息保障倍数", r"利息保障倍数\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)", "ratio"),
    ("ROE", r"(?:净资产收益率|ROE)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("毛利率", r"毛利率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("经营现金流/净利润", r"经营(?:活动)?现金流量净额\s*/\s*净利润\s*[:：]?\s*(-?[0-9]+(?:\.[0-9]+)?)", "ratio"),
    ("商誉占比", r"商誉\s*(?:占净资产)?(?:比例|占比)?\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("客户集中度", r"(?:前五大客户|客户集中度)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*%", "ratio"),
    ("供应商集中度", r"(?:前五大供应商|供应商集中度)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)\s*%", "ratio"),
    ("产能利用率", r"产能利用率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("对外担保比例", r"对外担保[^0-9%]{0,16}([0-9]+(?:\.[0-9]+)?)\s*%", "ratio"),
    ("关联交易占比", r"关联交易[^0-9%]{0,16}([0-9]+(?:\.[0-9]+)?)\s*%", "ratio"),
    ("股权质押率", r"(?:股权)?质押率\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", "ratio"),
    ("担保链层级", r"担保链[^0-9]{0,8}([0-9]+)\s*层", "count"),
]

# 这些指标若原文带 %，需要 /100
PERCENT_NAMES = {
    "资产负债率",
    "ROE",
    "毛利率",
    "商誉占比",
    "客户集中度",
    "供应商集中度",
    "产能利用率",
    "对外担保比例",
    "关联交易占比",
    "股权质押率",
}


def extract_text_from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    return path.read_text(encoding="utf-8-sig")


def _to_value(name: str, raw: str, matched_percent: bool) -> float:
    val = float(raw)
    if name in PERCENT_NAMES:
        # 若原文明确有 %，或数值 > 1 视为百分数写法
        if matched_percent or val > 1.0:
            val = val / 100.0
    return val


def parse_metrics_from_text(text: str, *, source_ref: str) -> list[MetricValue]:
    metrics: list[MetricValue] = []
    seen: set[str] = set()
    for name, pattern, unit in METRIC_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1)
        span = m.group(0)
        matched_percent = "%" in span
        value = _to_value(name, raw, matched_percent)
        if name in seen:
            continue
        seen.add(name)
        metrics.append(
            MetricValue(
                name=name,
                value=value,
                unit=unit,
                tier=DataTier.L1,
                source=MetricSource(type="document", ref=source_ref, page=None),
                confidence=0.8,
            )
        )

    # 正则命中偏少时：LLM 只做字段定位，数值必须在原文出现（Number Gate）
    if len(metrics) < 3:
        metrics.extend(_llm_locate_metrics(text, source_ref=source_ref, seen=seen))
    return metrics


def _llm_locate_metrics(
    text: str,
    *,
    source_ref: str,
    seen: set[str],
) -> list[MetricValue]:
    from bizatlas.llm.number_gate import extract_numbers, number_gate
    from bizatlas.llm.polish import llm_json
    from bizatlas.rules.nl_compiler import _ALLOWED_METRICS

    snippet = (text or "")[:3500]
    if not snippet.strip():
        return []
    allowed_names = "、".join(sorted(_ALLOWED_METRICS))
    data = llm_json(
        "从资料片段中定位财务指标。输出 JSON：{items:[{name, value, percent?:bool}]}\n"
        f"name 必须属于：{allowed_names}\n"
        "value 必须是原文中出现过的数字；禁止推算。找不到则 items 为空。\n"
        f"【资料】\n{snippet}"
    )
    if not data:
        return []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    text_nums = set(extract_numbers(snippet))
    # also allow raw integers as written
    unit_by_name = {n: u for n, _p, u in METRIC_PATTERNS}
    out: list[MetricValue] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in _ALLOWED_METRICS or name in seen:
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        percent = bool(item.get("percent"))
        # value must appear in source text (as ratio or percent)
        candidates = {value, value / 100.0 if value > 1 else value * 100.0}
        if not any(any(abs(c - t) < 0.051 for t in text_nums) for c in candidates):
            continue
        if name in PERCENT_NAMES and (percent or value > 1.0):
            value = value / 100.0
        # double-check serialized form against text allowlist
        ok, _ = number_gate(str(item.get("value")), text_nums | {value, value * 100})
        if not ok and value not in text_nums and (value * 100) not in text_nums:
            continue
        seen.add(name)
        out.append(
            MetricValue(
                name=name,
                value=value,
                unit=unit_by_name.get(name, "ratio"),
                tier=DataTier.L1,
                source=MetricSource(type="document", ref=source_ref, page=None),
                confidence=0.65,
            )
        )
    return out


def parse_metrics_document(path: str | Path) -> list[MetricValue]:
    """兼容入口：支持 .pdf（带证据链）与 .txt/.其他（纯文本）。

    需要证据链（带页码/文档哈希/坐标的 Evidence）请改用 parse_pdf_with_evidence（仅 PDF）。
    """
    file_path = Path(path)
    if file_path.suffix.lower() == ".pdf":
        return parse_pdf_with_evidence(file_path).metrics
    text = extract_text_from_file(file_path)
    return parse_metrics_from_text(text, source_ref=file_path.name)


class PageText(BaseModel):
    index: int  # 0-based 页码
    text: str


class ParseResult(BaseModel):
    metrics: list[MetricValue] = Field(default_factory=list)
    evidences: list[Evidence] = Field(default_factory=list)
    pages: list[PageText] = Field(default_factory=list)


def extract_pages_from_pdf(path: Path) -> list[PageText]:
    """逐页抽取文本，保留页码信息（引用定位的基础）。

    阶段 1 之前用 pypdf 一次性拼成纯文本，导致所有指标 page=None，无法回链原始位置。
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [PageText(index=i, text=page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_metrics_from_pages(
    pages: list[PageText],
    *,
    source_ref: str,
    doc_sha256: str | None = None,
) -> ParseResult:
    """逐页解析指标并产出带页码/文档哈希的 Evidence（引用定位核心）。"""
    metrics: list[MetricValue] = []
    evidences: list[Evidence] = []
    seen: set[str] = set()

    for name, pattern, unit in METRIC_PATTERNS:
        if name in seen:
            continue
        hit_page: int | None = None
        hit_span: str | None = None
        for pt in pages:
            m = re.search(pattern, pt.text, flags=re.IGNORECASE)
            if m:
                hit_page = pt.index
                hit_span = m.group(0)
                break
        if hit_page is None:
            continue
        m = re.search(pattern, pages[hit_page].text, flags=re.IGNORECASE)
        raw = m.group(1)
        matched_percent = "%" in (hit_span or "")
        value = _to_value(name, raw, matched_percent)
        seen.add(name)

        ev_id = uuid.uuid4().hex
        evidences.append(
            Evidence(
                evidence_id=ev_id,
                source_type="document",
                page=hit_page + 1,
                bbox=None,  # 纯文本路径无坐标；视觉分支（vision.py）会补全
                doc_sha256=doc_sha256,
                content_snippet=(hit_span or "").strip(),
            )
        )
        metrics.append(
            MetricValue(
                name=name,
                value=value,
                unit=unit,
                tier=DataTier.L1,
                source=MetricSource(type="document", ref=source_ref, page=hit_page + 1),
                evidence_refs=[ev_id],
                confidence=0.8,
            )
        )

    if len(metrics) < 3:
        extra = _llm_locate_metrics_pages(pages, source_ref=source_ref, seen=seen, doc_sha256=doc_sha256)
        metrics.extend(extra.metrics)
        evidences.extend(extra.evidences)

    return ParseResult(metrics=metrics, evidences=evidences, pages=pages)


def parse_pdf_with_evidence(path: str | Path) -> ParseResult:
    """解析 PDF 并产出指标 + Evidence。阶段 1 主入口。"""
    file_path = Path(path)
    pages = extract_pages_from_pdf(file_path)
    doc_sha256 = _sha256_file(file_path)
    return parse_metrics_from_pages(pages, source_ref=file_path.name, doc_sha256=doc_sha256)


def _llm_locate_metrics_pages(
    pages: list[PageText],
    *,
    source_ref: str,
    seen: set[str],
    doc_sha256: str | None = None,
) -> ParseResult:
    """LLM 只在正则命中偏少时做字段定位；数值必须原文出现（Number Gate）。

    与纯文本版本不同的是：逐页拼接带页码前缀，定位每条指标的所在页。
    """
    from bizatlas.llm.number_gate import extract_numbers, number_gate
    from bizatlas.llm.polish import llm_json
    from bizatlas.rules.nl_compiler import _ALLOWED_METRICS

    parts: list[str] = []
    for pt in pages:
        seg = (pt.text or "")[:3500]
        if seg.strip():
            parts.append(f"[PAGE {pt.index + 1}]\n{seg}")
    snippet = "\n".join(parts)
    if not snippet.strip():
        return ParseResult()

    allowed_names = "、".join(sorted(_ALLOWED_METRICS))
    data = llm_json(
        "从资料片段中定位财务指标。输出 JSON：{items:[{name, value, percent?:bool}]}\n"
        f"name 必须属于：{allowed_names}\n"
        "value 必须是原文中出现过的数字；禁止推算。找不到则 items 为空。\n"
        f"【资料】\n{snippet}"
    )
    if not data:
        return ParseResult()
    items = data.get("items") if isinstance(data.get("items"), list) else []

    page_nums = [(pt.index, set(extract_numbers(pt.text))) for pt in pages]
    text_nums = set().union(*[s for _, s in page_nums]) if page_nums else set()
    unit_by_name = {n: u for n, _p, u in METRIC_PATTERNS}
    out_metrics: list[MetricValue] = []
    out_evidences: list[Evidence] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in _ALLOWED_METRICS or name in seen:
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        percent = bool(item.get("percent"))
        candidates = {value, value / 100.0 if value > 1 else value * 100.0}
        if not any(any(abs(c - t) < 0.051 for t in text_nums) for c in candidates):
            continue
        if name in PERCENT_NAMES and (percent or value > 1.0):
            value = value / 100.0
        ok, _ = number_gate(str(item.get("value")), text_nums | {value, value * 100})
        if not ok and value not in text_nums and (value * 100) not in text_nums:
            continue
        hit_page: int | None = None
        for pidx, nums in page_nums:
            if any(abs(c - t) < 0.051 for c in candidates for t in nums):
                hit_page = pidx
                break
        seen.add(name)
        ev_id = uuid.uuid4().hex
        page_no = hit_page + 1 if hit_page is not None else None
        out_evidences.append(
            Evidence(
                evidence_id=ev_id,
                source_type="document",
                page=page_no,
                bbox=None,
                doc_sha256=doc_sha256,
                content_snippet=str(item.get("value")),
            )
        )
        out_metrics.append(
            MetricValue(
                name=name,
                value=value,
                unit=unit_by_name.get(name, "ratio"),
                tier=DataTier.L1,
                source=MetricSource(type="document", ref=source_ref, page=page_no),
                evidence_refs=[ev_id],
                confidence=0.65,
            )
        )
    return ParseResult(metrics=out_metrics, evidences=out_evidences, pages=pages)
