from __future__ import annotations

from pathlib import Path
import uuid

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

from bizatlas.contracts.models import Evidence, MetricValue
from bizatlas.data import repo
from bizatlas.ingest.excel_metrics import parse_metrics_excel
from bizatlas.ingest.pdf_metrics import parse_metrics_document, parse_pdf_with_evidence
from bizatlas.ingest.vision import run_vision_pipeline

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".pdf"}


def ingest_metrics_file(company_id: str, filename: str, content: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"支持格式：{', '.join(sorted(SUPPORTED_SUFFIXES))}。"
            "CSV 用 name,value；PDF/TXT 用关键指标中文表述。"
            "模板见 content/templates/"
        )

    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB）")
    dest_dir = repo.upload_dir_for(company_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name  # 去除目录成分，防路径遍历
    suffix = Path(safe_name).suffix.lower()
    dest = dest_dir / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(content)

    metrics: list[MetricValue]
    evidences: list[Evidence] = []
    parser = "csv"
    vision = None
    pages: int | None = None
    if suffix in {".csv", ".tsv"}:
        metrics = parse_metrics_excel(dest)
        parser = "csv"
    elif suffix == ".pdf":
        parsed = parse_pdf_with_evidence(dest)
        metrics = parsed.metrics
        evidences = parsed.evidences
        pages = len(parsed.pages)
        parser = "pdf_text"
        # 阶段 1：视觉优先分支（扫描件/印章/复杂表格检测；默认降级）
        vision = run_vision_pipeline(dest, dest.name).model_dump(mode="json")
    else:
        metrics = parse_metrics_document(dest)
        parser = "text"

    if not metrics:
        repo.save_document(company_id, filename, dest, status="failed")
        raise ValueError(
            "未解析到任何指标。CSV 请检查表头 name,value；"
            "PDF/TXT 请包含如「流动比率」「资产负债率」等字段。"
        )

    for m in metrics:
        if m.source:
            m.source.ref = dest.name

    count = repo.replace_metrics(company_id, metrics)
    if evidences:
        repo.save_evidence(company_id, evidences)
    doc_id = repo.save_document(company_id, filename, dest, status="parsed")

    # index for local RAG
    try:
        from bizatlas.rag.simple import index_text

        if suffix in {".pdf", ".txt"}:
            text = dest.read_text(encoding="utf-8", errors="ignore") if suffix == ".txt" else None
            if text is None:
                from bizatlas.ingest.pdf_metrics import extract_text_from_pdf

                text = extract_text_from_pdf(dest)
            index_text(doc_id, text or "")
        else:
            # csv: index as plain text rows
            index_text(doc_id, dest.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:  # noqa: BLE001
        pass

    return {
        "document_id": doc_id,
        "filename": filename,
        "parser": parser,
        "metrics_count": count,
        "evidence_count": len(evidences),
        "pages": pages,
        "vision": vision,
        "metrics": [m.model_dump(mode="json") for m in metrics],
    }
