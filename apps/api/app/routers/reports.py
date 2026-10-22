from __future__ import annotations

from bizatlas.auth.rbac import Action, Principal
from bizatlas.contracts.models import Envelope
from bizatlas.data import repo
from bizatlas.industry.benchmarks import compare_to_industry, load_benchmarks
from bizatlas.orchestrator.analyze import generate_credit_report, generate_onepager_report
from bizatlas.report.onepager import render_onepager_markdown
from bizatlas.report.titles import make_analysis_title, status_label
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from apps.api.app.main import (
    ReportRequest,
)
from apps.api.auth_deps import get_principal

router = APIRouter()

@router.post("/v1/reports")
def create_report(
    req: ReportRequest,
    principal: Principal = Depends(get_principal),
) -> Envelope[dict]:
    # 阶段 3：落盘导出属于敏感操作，需要 export_reports 权限
    if req.confirm and not principal.can(Action.EXPORT_REPORTS):
        raise HTTPException(
            status_code=403,
            detail=f"role {principal.role.value} 无权导出报告（需要 reports:export）",
        )
    try:
        if req.template_id == "credit_assessment":
            result = generate_credit_report(req.company_id, confirm_export=req.confirm)
        else:
            result = generate_onepager_report(req.company_id, confirm_export=req.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(
        ok=True,
        data=result,
        meta={
            "human_gate": "confirm=true required for filesystem export",
            "exported": bool(
                result.get("export_path") or result.get("docx_path") or result.get("pdf_path")
            ),
            "template_id": req.template_id,
        },
    )

@router.get("/v1/industry/benchmarks")
def industry_benchmarks(industry: str | None = None) -> Envelope[dict]:

    if industry:
        return Envelope(ok=True, data=compare_to_industry(industry, []))
    return Envelope(ok=True, data=load_benchmarks())

@router.get("/v1/reports-list")
def reports_list() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_reports())

@router.get("/v1/reports/{report_id}")
def get_report(report_id: str) -> Envelope[dict]:

    row = repo.get_report(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    payload = row.get("payload") or {}
    title = payload.get("analysis_title") or make_analysis_title(
        payload.get("company") or {},
        {"grade": payload.get("grade")},
        str(row.get("template_id") or "risk_onepager"),
    )
    return Envelope(
        ok=True,
        data={
            **row,
            "title": title,
            "status_label": status_label(row.get("status")),
        },
    )

@router.get("/v1/reports/{report_id}/markdown")
def get_report_markdown(report_id: str) -> PlainTextResponse:
    from bizatlas.report.titles import make_analysis_title

    row = repo.get_report(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    payload = row["payload"] or {}
    title = payload.get("analysis_title") or make_analysis_title(
        payload.get("company") or {},
        {"grade": payload.get("grade")},
        str(row.get("template_id") or "risk_onepager"),
    )
    if payload.get("template_id") == "credit_assessment" or row.get("template_id") == "credit_assessment":
        lines = [f"# {title}", "", f"> {payload.get('headline', '')}", ""]
        for section in payload.get("sections") or []:
            lines.append(f"## {section.get('title', '')}")
            if section.get("body"):
                lines.append(str(section["body"]))
            for b in section.get("bullets") or []:
                lines.append(f"- {b}")
            lines.append("")
        md = "\n".join(lines)
    else:
        md = render_onepager_markdown(payload)
        if title and not md.startswith(f"# {title}"):
            md = f"# {title}\n\n{md}"
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")

