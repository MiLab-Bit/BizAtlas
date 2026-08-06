from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from bizatlas.config import get_settings
from bizatlas.contracts.models import AnalyzeRequest, Envelope, HealthData
from bizatlas.data import repo
from bizatlas.data.db import init_db
from bizatlas.data.registry import provider_health_list
from bizatlas.ingest.fixtures import list_fixtures
from bizatlas.ingest.upload import ingest_metrics_file
from bizatlas.kg.graph import build_guarantee_graph
from bizatlas.orchestrator.analyze import (
    generate_credit_report,
    generate_onepager_report,
    run_analyze,
)
from bizatlas.rules.nl_compiler import compile_rule_from_nl
from bizatlas.rules.store import activate_rule, load_all_rules, save_pilot_rule
from bizatlas.workflow.due_diligence import (
    advance_due_diligence,
    get_due_diligence,
    start_due_diligence,
)

settings = get_settings()

app = FastAPI(title="BizAtlas API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateCompanyRequest(BaseModel):
    name: str
    industry: str = ""


class ReportRequest(BaseModel):
    company_id: str
    template_id: str = "risk_onepager"  # risk_onepager | credit_assessment
    confirm: bool = Field(default=False, description="True to write export files")


class NlRuleRequest(BaseModel):
    text: str
    activate: bool = False


class ChatRequest(BaseModel):
    message: str
    company_id: str | None = None
    fixture_id: str | None = None
    context: dict | None = None


class BackgroundStartRequest(BaseModel):
    company_name: str
    industry: str = ""


class BackgroundChatRequest(BaseModel):
    company_name: str
    message: str
    company_id: str | None = None
    fixture_id: str | None = None
    history: list[dict] | None = None


class AkshareFetchRequest(BaseModel):
    symbol: str
    company_id: str | None = None
    company_name: str | None = None


class StartWorkflowRequest(BaseModel):
    company_id: str | None = None
    fixture_id: str | None = None
    name: str | None = None
    industry: str = ""


class AdvanceWorkflowRequest(BaseModel):
    action: str  # sync | mark | analyze | report | submit
    confirm: bool = False
    manual_flags: dict[str, bool] | None = None


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/v1/health")
def health() -> Envelope[HealthData]:
    db_ok = False
    try:
        init_db()
        db_ok = True
    except Exception:
        db_ok = False
    from bizatlas.llm.client import llm_configured

    data = HealthData(
        mode=settings.bizatlas_mode,
        providers=provider_health_list(),
        db_ok=db_ok,
        rules_loaded=len(load_all_rules()),
        llm_configured=llm_configured(),
        llm_model=settings.llm_model if llm_configured() else "",
    )
    return Envelope(
        ok=True,
        data=data,
        meta={"request_id": "health", "mode": settings.bizatlas_mode, "degraded": False},
    )


@app.get("/v1/fixtures")
def fixtures() -> Envelope[list[str]]:
    return Envelope(ok=True, data=list_fixtures(), meta={"mode": settings.bizatlas_mode})


@app.get("/v1/companies")
def companies() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_companies())


@app.post("/v1/companies")
def create_company(req: CreateCompanyRequest) -> Envelope[dict]:
    created = repo.create_company(req.name, req.industry)
    return Envelope(ok=True, data=created)


@app.get("/v1/companies/{company_id}")
def get_company(company_id: str) -> Envelope[dict]:
    company = repo.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    metrics = repo.load_metrics(company_id)
    return Envelope(
        ok=True,
        data={**company, "metrics_count": len(metrics), "metrics": [m.model_dump(mode="json") for m in metrics]},
    )


@app.post("/v1/companies/{company_id}/documents")
async def upload_document(
    company_id: str,
    file: UploadFile = File(...),
) -> Envelope[dict]:
    if not repo.get_company(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    content = await file.read()
    try:
        result = ingest_metrics_file(company_id, file.filename or "metrics.csv", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(ok=True, data=result, meta={"degraded": False})


@app.post("/v1/analyze")
def analyze(req: AnalyzeRequest) -> Envelope[dict]:
    try:
        result = run_analyze(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    degraded = result.get("metrics_count", 0) == 0
    return Envelope(
        ok=True,
        data=result,
        meta={
            "request_id": result.get("task_id"),
            "mode": settings.bizatlas_mode,
            "degraded": degraded,
        },
    )


@app.post("/v1/reports")
def create_report(req: ReportRequest) -> Envelope[dict]:
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


@app.get("/v1/industry/benchmarks")
def industry_benchmarks(industry: str | None = None) -> Envelope[dict]:
    from bizatlas.industry.benchmarks import compare_to_industry, load_benchmarks

    if industry:
        return Envelope(ok=True, data=compare_to_industry(industry, []))
    return Envelope(ok=True, data=load_benchmarks())


@app.get("/v1/reports-list")
def reports_list() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_reports())


@app.get("/v1/companies/{company_id}/graph")
def company_graph(company_id: str, fixture_id: str | None = None) -> Envelope[dict]:
    fid = fixture_id
    if company_id in {"healthy", "risky", "defaulted"}:
        fid = company_id
    data = build_guarantee_graph(company_id, fixture_id=fid)
    return Envelope(ok=True, data=data)


@app.post("/v1/chat")
def chat(req: ChatRequest) -> Envelope[dict]:
    from bizatlas.llm.agent import handle_agent_message

    try:
        result = handle_agent_message(
            req.message.strip(),
            company_id=req.company_id,
            fixture_id=req.fixture_id,
            context=req.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Envelope(ok=True, data=result)


@app.post("/v1/background/start")
def background_start(req: BackgroundStartRequest) -> Envelope[dict]:
    from bizatlas.llm.background import start_background_session

    try:
        data = start_background_session(req.company_name, industry=req.industry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)


@app.post("/v1/background/chat")
def background_chat(req: BackgroundChatRequest) -> Envelope[dict]:
    from bizatlas.llm.background import background_reply

    try:
        data = background_reply(
            req.message,
            company_id=req.company_id,
            company_name=req.company_name,
            fixture_id=req.fixture_id,
            history=req.history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)


@app.post("/v1/rules/from-nl")
def rules_from_nl(req: NlRuleRequest) -> Envelope[dict]:
    try:
        rule = compile_rule_from_nl(req.text)
        saved = save_pilot_rule(rule)
        if req.activate:
            saved = activate_rule(saved["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(
        ok=True,
        data=saved,
        meta={"pilot": saved.get("status") == "pilot", "human_gate": "activate requires confirm path"},
    )


@app.post("/v1/rules/{rule_id}/activate")
def rules_activate(rule_id: str, confirm: bool = False) -> Envelope[dict]:
    if not confirm:
        raise HTTPException(status_code=409, detail="激活规则需要 confirm=true")
    try:
        saved = activate_rule(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(ok=True, data=saved)


@app.post("/v1/providers/akshare/fetch")
def akshare_fetch(req: AkshareFetchRequest) -> Envelope[dict]:
    from bizatlas.contracts.models import DataTier, MetricSource, MetricValue
    from bizatlas.data.providers_akshare import fetch_stock_basic_metrics

    try:
        items = fetch_stock_basic_metrics(req.symbol)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    company_id = req.company_id
    if not company_id:
        company = repo.create_company(req.company_name or f"AKShare-{req.symbol}", "上市")
        company_id = company["id"]
    metrics = [
        MetricValue(
            name=i["name"],
            value=i.get("value"),
            unit=i.get("unit", "ratio"),
            tier=DataTier(i.get("tier", "L1")),
            source=MetricSource(**(i.get("source") or {"type": "api", "ref": "akshare"})),
            confidence=float(i.get("confidence", 0.7)),
        )
        for i in items
    ]
    repo.replace_metrics(company_id, metrics)
    return Envelope(
        ok=True,
        data={"company_id": company_id, "metrics_count": len(metrics), "metrics": items},
    )


@app.get("/v1/reports/{report_id}")
def get_report(report_id: str) -> Envelope[dict]:
    from bizatlas.report.titles import make_analysis_title, status_label

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


@app.get("/v1/reports/{report_id}/markdown")
def get_report_markdown(report_id: str) -> PlainTextResponse:
    from bizatlas.report.onepager import render_onepager_markdown
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


@app.post("/v1/workflows/due-diligence")
def start_workflow(req: StartWorkflowRequest) -> Envelope[dict]:
    try:
        data = start_due_diligence(
            company_id=req.company_id,
            fixture_id=req.fixture_id,
            name=req.name,
            industry=req.industry,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)


@app.get("/v1/workflows")
def workflows() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_workflows())


@app.get("/v1/workflows/{workflow_id}")
def workflow_detail(workflow_id: str) -> Envelope[dict]:
    try:
        data = get_due_diligence(workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)


@app.post("/v1/workflows/{workflow_id}/advance")
def workflow_advance(workflow_id: str, req: AdvanceWorkflowRequest) -> Envelope[dict]:
    try:
        data = advance_due_diligence(
            workflow_id,
            action=req.action,
            confirm=req.confirm,
            manual_flags=req.manual_flags,
        )
    except ValueError as exc:
        status = 409 if "confirm" in str(exc) or "齐套" in str(exc) or "先" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return Envelope(
        ok=True,
        data=data,
        meta={"action": req.action, "human_gate": req.action == "submit"},
    )


@app.get("/v1/rules")
def rules() -> Envelope[list[dict]]:
    loaded = load_all_rules()
    summary = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "dimension": r.get("dimension"),
            "severity": r.get("severity"),
            "status": r.get("status", "active"),
            "contribute_to_score": r.get("contribute_to_score", True),
        }
        for r in loaded
    ]
    return Envelope(ok=True, data=summary, meta={"count": len(summary)})


# Optional quick create+upload helper for demos
@app.post("/v1/quick/upload-analyze")
async def quick_upload_analyze(
    name: str = Form("上传企业"),
    industry: str = Form(""),
    file: UploadFile = File(...),
) -> Envelope[dict]:
    company = repo.create_company(name, industry)
    content = await file.read()
    try:
        ingested = ingest_metrics_file(company["id"], file.filename or "metrics.csv", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    analyzed = run_analyze(
        AnalyzeRequest(company_id=company["id"], intent="gen_report", template_id="risk_onepager")
    )
    return Envelope(
        ok=True,
        data={"company": company, "ingest": ingested, "analyze": analyzed},
        meta={"degraded": analyzed.get("metrics_count", 0) == 0},
    )
