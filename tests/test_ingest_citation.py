from __future__ import annotations

import uuid
from pathlib import Path

from bizatlas.contracts.models import Evidence
from bizatlas.ingest.pdf_metrics import parse_pdf_with_evidence
from bizatlas.ingest.vision import DocumentLayoutType, detect_document_type, run_vision_pipeline


def _make_pdf(path: Path, pages: list[str]) -> None:
    """生成含中文的真实多页 PDF（用 reportlab 自带 CID 字体，无需外部字体文件）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:  # noqa: BLE001
        pass
    c = canvas.Canvas(str(path), pagesize=A4)
    for page_text in pages:
        y = 800
        for line in page_text.split("\n"):
            c.setFont("STSong-Light", 12)
            c.drawString(50, y, line)
            y -= 20
        c.showPage()
    c.save()


def test_parse_pdf_with_evidence_locates_pages(tmp_path):
    pdf = tmp_path / "report.pdf"
    _make_pdf(
        pdf,
        [
            "公司年度财报\n流动比率 2.5\n速动比率 1.2",
            "资产负债率 50%\nROE 12%",
        ],
    )
    res = parse_pdf_with_evidence(pdf)
    by_name = {m.name: m for m in res.metrics}

    # 页码级引用定位：不同指标回到正确页
    assert by_name["流动比率"].source.page == 1
    assert by_name["速动比率"].source.page == 1
    assert by_name["资产负债率"].source.page == 2
    assert by_name["ROE"].source.page == 2

    # 证据链闭合：每条指标有 evidence_refs，且 Evidence 页码/片段/哈希齐全
    ev_by_id = {e.evidence_id: e for e in res.evidences}
    for m in res.metrics:
        assert m.evidence_refs, f"{m.name} 缺 evidence_refs"
        ev = ev_by_id[m.evidence_refs[0]]
        assert ev.page == m.source.page
        assert ev.content_snippet
        assert len(ev.doc_sha256) == 64  # SHA256


def test_detect_document_type(tmp_path):
    normal = tmp_path / "n.pdf"
    _make_pdf(normal, ["流动比率 2.5\n资产负债率 50%"])
    assert detect_document_type(normal) == DocumentLayoutType.TEXT

    sealed = tmp_path / "s.pdf"
    _make_pdf(sealed, ["资产负债表\n（盖章）"])
    assert detect_document_type(sealed) == DocumentLayoutType.SEALED

    scanned = tmp_path / "e.pdf"
    _make_pdf(scanned, [""])  # 文字层为空 → 扫描件
    assert detect_document_type(scanned) == DocumentLayoutType.SCANNED


def test_vision_pipeline_degrades_when_disabled(tmp_path):
    pdf = tmp_path / "n.pdf"
    _make_pdf(pdf, ["流动比率 2.5"])
    r = run_vision_pipeline(pdf, "n.pdf")
    assert r.verified is False
    assert r.detected_type == "text"
    assert r.note  # 说明降级原因


def test_evidence_repo_roundtrip():
    from bizatlas.data import repo as repomod
    from bizatlas.data.db import init_db

    init_db()
    cid = f"ev-co-{uuid.uuid4().hex[:8]}"
    repomod.ensure_company(cid, "EvCo")
    evs = [
        Evidence(
            evidence_id="e1",
            source_type="document",
            page=1,
            bbox=None,
            doc_sha256="x" * 64,
            content_snippet="流动比率 2.5",
        )
    ]
    assert repomod.save_evidence(cid, evs) == 1
    got = repomod.list_evidence(cid)
    assert len(got) == 1 and got[0].evidence_id == "e1"


def test_ingest_pdf_evidence_and_load_roundtrip(tmp_path):
    from bizatlas.data import repo as repomod
    from bizatlas.data.db import init_db
    from bizatlas.ingest.upload import ingest_metrics_file

    init_db()
    cid = f"cite-co-{uuid.uuid4().hex[:8]}"
    repomod.ensure_company(cid, "CiteCo")

    pdf = tmp_path / "r.pdf"
    _make_pdf(pdf, ["流动比率 2.5\n资产负债率 50%"])
    content = pdf.read_bytes()

    result = ingest_metrics_file(cid, "r.pdf", content)
    assert result["evidence_count"] >= 1
    assert result["vision"] is not None
    assert result["vision"]["verified"] is False  # 默认降级

    # DB 层链路闭合：load_metrics 必须恢复 evidence_refs（否则证据链断）
    loaded = repomod.load_metrics(cid)
    assert any(m.evidence_refs for m in loaded)


def test_end_to_end_evidence_chain_closes(tmp_path):
    """证据链端到端闭合：ingest PDF → 入库 → run_analyze 的 RiskResult.evidence_refs 非空。

    验证阶段 1 之前 Phase 0 的 evidence_refs 只是孤儿 ID（无真实 Evidence）的缺陷已修复。
    """
    from bizatlas.contracts.models import AnalyzeRequest
    from bizatlas.data import repo as repomod
    from bizatlas.data.db import init_db
    from bizatlas.ingest.upload import ingest_metrics_file
    from bizatlas.orchestrator.analyze import run_analyze

    init_db()
    cid = f"e2e-{uuid.uuid4().hex[:8]}"
    repomod.ensure_company(cid, "E2E")

    pdf = tmp_path / "r.pdf"
    _make_pdf(pdf, ["流动比率 2.5\n速动比率 1.2\n资产负债率 50%\nROE 12%\n毛利率 28%"])
    ingest_metrics_file(cid, "r.pdf", pdf.read_bytes())

    out = run_analyze(AnalyzeRequest(company_id=cid))
    risk = out["risk"]
    assert len(risk.get("evidence_refs", [])) >= 1
