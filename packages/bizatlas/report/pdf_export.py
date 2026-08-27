from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


def _ensure_font() -> str:
    name = "STSong-Light"
    try:
        pdfmetrics.getFont(name)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def _draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, *, max_chars: int = 42, leading: float = 16) -> float:
    font = _ensure_font()
    c.setFont(font, 11)
    for i in range(0, len(text), max_chars):
        if y < 48:
            c.showPage()
            c.setFont(font, 11)
            y = A4[1] - 48
        c.drawString(x, y, text[i : i + max_chars])
        y -= leading
    return y


def export_report_pdf(payload: dict[str, Any], out_path: str | Path, *, kind: str = "onepager") -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    font = _ensure_font()
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 48

    title = str(payload.get("title") or ("企业信用评估报告" if kind == "credit" else "一页风险摘要"))
    c.setFont(font, 16)
    c.drawString(48, y, title[:40])
    y -= 28

    company = payload.get("company") or {}
    head = (
        f"企业：{company.get('name', '—')}  行业：{company.get('industry') or '—'}  "
        f"等级：{payload.get('grade')}  得分：{payload.get('score')}"
    )
    y = _draw_wrapped(c, head, 48, y)
    y -= 8
    if payload.get("headline"):
        y = _draw_wrapped(c, str(payload["headline"]), 48, y)
        y -= 10

    if kind == "credit":
        sections = payload.get("sections") or []
        for section in sections:
            if y < 80:
                c.showPage()
                y = height - 48
            c.setFont(font, 13)
            c.drawString(48, y, str(section.get("title") or "")[:40])
            y -= 20
            if section.get("body"):
                y = _draw_wrapped(c, str(section["body"]), 48, y)
            for b in section.get("bullets") or []:
                y = _draw_wrapped(c, f"• {b}", 56, y, max_chars=40)
            y -= 8
    else:
        c.setFont(font, 13)
        c.drawString(48, y, "五维风险")
        y -= 18
        for d in payload.get("dimensions") or []:
            y = _draw_wrapped(c, f"- {d.get('id')}: {d.get('score')}（权重 {d.get('weight')}）", 48, y)
        y -= 8
        c.setFont(font, 13)
        if y < 80:
            c.showPage()
            y = height - 48
        c.drawString(48, y, "Top 风险点")
        y -= 18
        tops = payload.get("top_risks") or []
        if not tops:
            y = _draw_wrapped(c, "- 暂无规则命中", 48, y)
        for h in tops:
            y = _draw_wrapped(
                c,
                f"[{h.get('severity')}] {h.get('message')} — {h.get('explain', '')}",
                48,
                y,
            )
        if payload.get("disclaimer"):
            y -= 10
            y = _draw_wrapped(c, str(payload["disclaimer"]), 48, y)

    y -= 12
    _draw_wrapped(c, "— 完 —（数字来自计算管线，非模型编造）", 48, max(y, 48))
    c.save()
    return path
