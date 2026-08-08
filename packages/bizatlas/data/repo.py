from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from bizatlas.config import get_settings
from bizatlas.contracts.models import Evidence, MetricValue
from bizatlas.data.db import get_connection


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_company(name: str, industry: str = "") -> dict[str, Any]:
    company_id = f"co-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO companies (id, name, industry, created_at) VALUES (?, ?, ?, ?)",
            (company_id, name, industry, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": company_id, "name": name, "industry": industry}


def save_evidence(company_id: str, evidence: list[Evidence]) -> int:
    """持久化证据链：每条 MetricValue/RuleHit 关联的 Evidence 落到 evidence 表。

    阶段 1 之前，RiskResult.evidence_refs 只是孤儿 ID；现在解析阶段真正产出
    并存储 Evidence，证据链才闭合、可审计（见 contracts/integrity 防篡改）。
    """
    if not evidence:
        return 0
    conn = get_connection()
    try:
        for ev in evidence:
            conn.execute(
                "INSERT INTO evidence "
                "(id, company_id, evidence_id, source_type, doc_id, page, bbox, doc_sha256, content_snippet, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"ev-{uuid.uuid4().hex[:12]}",
                    company_id,
                    ev.evidence_id,
                    ev.source_type,
                    ev.doc_id,
                    ev.page,
                    ev.bbox,
                    ev.doc_sha256,
                    ev.content_snippet,
                    _now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(evidence)


def list_evidence(company_id: str) -> list[Evidence]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT evidence_id, source_type, doc_id, page, bbox, doc_sha256, content_snippet, created_at "
            "FROM evidence WHERE company_id = ? ORDER BY created_at ASC",
            (company_id,),
        ).fetchall()
    finally:
        conn.close()
    return [Evidence(**dict(r)) for r in rows]


def get_company(company_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, industry, created_at FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_companies(limit: int = 50) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, industry, created_at FROM companies ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_document(
    company_id: str,
    filename: str,
    dest: Path,
    status: str = "parsed",
) -> str:
    doc_id = f"doc-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO documents (id, company_id, filename, path, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, company_id, filename, str(dest), status, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return doc_id


def replace_metrics(company_id: str, metrics: list[MetricValue]) -> int:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM financial_metrics WHERE company_id = ?", (company_id,))
        for m in metrics:
            mid = f"m-{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO financial_metrics "
                "(id, company_id, name, value, unit, tier, as_of, source_json, evidence_refs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mid,
                    company_id,
                    m.name,
                    m.value,
                    m.unit,
                    m.tier.value,
                    m.as_of.isoformat() if m.as_of else None,
                    m.source.model_dump_json() if m.source else "{}",
                    json.dumps(m.evidence_refs or [], ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return len(metrics)


def load_metrics(company_id: str) -> list[MetricValue]:
    from bizatlas.contracts.models import DataTier, MetricSource

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, value, unit, tier, as_of, source_json, evidence_refs "
            "FROM financial_metrics WHERE company_id = ?",
            (company_id,),
        ).fetchall()
    finally:
        conn.close()

    out: list[MetricValue] = []
    for r in rows:
        src_raw = json.loads(r["source_json"] or "{}")
        source = MetricSource(**src_raw) if src_raw else None
        ev_refs = json.loads(r["evidence_refs"] or "[]") if r["evidence_refs"] else []
        out.append(
            MetricValue(
                name=r["name"],
                value=r["value"],
                unit=r["unit"] or "",
                tier=DataTier(r["tier"] or "L1"),
                source=source,
                evidence_refs=ev_refs,
                confidence=0.95,
            )
        )
    return out


def save_risk_score(company_id: str, risk_payload: dict[str, Any]) -> str:
    rid = f"rs-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO risk_scores (id, company_id, grade, score, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                rid,
                company_id,
                risk_payload.get("grade"),
                risk_payload.get("score"),
                json.dumps(risk_payload, ensure_ascii=False),
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return rid


def save_report(
    company_id: str,
    template_id: str,
    payload: dict[str, Any],
    status: str = "generated",
) -> str:
    report_id = f"rp-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO reports (id, company_id, template_id, status, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                report_id,
                company_id,
                template_id,
                status,
                json.dumps(payload, ensure_ascii=False),
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return report_id


def list_reports(limit: int = 40) -> list[dict[str, Any]]:
    from bizatlas.report.titles import make_analysis_title, status_label

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, company_id, template_id, status, payload_json, created_at FROM reports "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            payload = json.loads(item.pop("payload_json") or "{}")
            company = payload.get("company") or {}
            title = payload.get("analysis_title") or make_analysis_title(
                company,
                {"grade": payload.get("grade")},
                str(item.get("template_id") or "risk_onepager"),
            )
            kind = (
                "信用背调"
                if item.get("template_id") == "credit_assessment"
                else "风险摘要"
            )
            out.append(
                {
                    "id": item["id"],
                    "company_id": item["company_id"],
                    "company_name": company.get("name") or item["company_id"],
                    "template_id": item.get("template_id"),
                    "kind": kind,
                    "title": title,
                    "grade": payload.get("grade"),
                    "headline": payload.get("headline"),
                    "status": item.get("status"),
                    "status_label": status_label(item.get("status")),
                    "created_at": item.get("created_at"),
                }
            )
        return out
    finally:
        conn.close()


def get_report(report_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, company_id, template_id, status, payload_json, created_at "
            "FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        return data
    finally:
        conn.close()


def upload_dir_for(company_id: str) -> Path:
    settings = get_settings()
    path = Path(settings.bizatlas_upload_dir) / company_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_dir() -> Path:
    settings = get_settings()
    path = Path(settings.bizatlas_export_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_company(company_id: str, name: str, industry: str = "") -> dict[str, Any]:
    existing = get_company(company_id)
    if existing:
        return existing
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO companies (id, name, industry, created_at) VALUES (?, ?, ?, ?)",
            (company_id, name, industry, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": company_id, "name": name, "industry": industry}


def save_workflow(
    template_id: str,
    company_id: str,
    stage: str,
    payload: dict[str, Any],
    workflow_id: str | None = None,
) -> str:
    wid = workflow_id or f"wf-{uuid.uuid4().hex[:10]}"
    conn = get_connection()
    try:
        if workflow_id:
            conn.execute(
                "UPDATE workflows SET stage = ?, payload_json = ?, updated_at = ? WHERE id = ?",
                (stage, json.dumps(payload, ensure_ascii=False), _now(), wid),
            )
        else:
            conn.execute(
                "INSERT INTO workflows "
                "(id, template_id, company_id, stage, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    wid,
                    template_id,
                    company_id,
                    stage,
                    json.dumps(payload, ensure_ascii=False),
                    _now(),
                    _now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return wid


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, template_id, company_id, stage, payload_json, created_at, updated_at "
            "FROM workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        return data
    finally:
        conn.close()


def list_workflows(limit: int = 30) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, template_id, company_id, stage, created_at, updated_at "
            "FROM workflows ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

