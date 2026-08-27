from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.ingest.pdf_metrics import parse_metrics_document, parse_metrics_from_text


def test_parse_txt_excerpt():
    path = ROOT / "content" / "templates" / "sample_financial_excerpt.txt"
    metrics = parse_metrics_document(path)
    names = {m.name for m in metrics}
    assert "流动比率" in names
    assert "资产负债率" in names
    assert "客户集中度" in names
    al = next(m for m in metrics if m.name == "资产负债率")
    assert 0.7 < (al.value or 0) < 0.85
    cr = next(m for m in metrics if m.name == "流动比率")
    assert abs((cr.value or 0) - 0.85) < 1e-6


def test_parse_percent_and_ratio_mix():
    text = "流动比率：1.2\n毛利率：28%\n担保链共 3 层\n"
    metrics = parse_metrics_from_text(text, source_ref="t.txt")
    by = {m.name: m.value for m in metrics}
    assert by["流动比率"] == 1.2
    assert abs((by["毛利率"] or 0) - 0.28) < 1e-6
    assert by["担保链层级"] == 3
