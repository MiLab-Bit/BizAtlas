"""Generate sample PDF from financial excerpt for demo upload."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "content" / "templates" / "sample_financial_excerpt.txt"
OUT = ROOT / "content" / "templates" / "sample_financial_excerpt.pdf"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(OUT), pagesize=A4)
    width, height = A4
    c.setFont("STSong-Light", 11)
    y = height - 48
    for line in text.splitlines():
        if y < 48:
            c.showPage()
            c.setFont("STSong-Light", 11)
            y = height - 48
        c.drawString(48, y, line[:80])
        y -= 16
    c.save()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
