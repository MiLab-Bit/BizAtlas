from __future__ import annotations

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.orchestrator.trace import build_trace
from bizatlas.rules.nl_compiler import compile_rule_from_nl
from bizatlas.rules.store import activate_rule, load_all_rules, save_pilot_rule
from bizatlas.workflow.due_diligence import (
    advance_due_diligence,
    get_due_diligence,
    review_due_diligence,
    start_due_diligence,
)

from bizatlas.auth.rbac import Action, Principal, Role
from bizatlas.identity import (
    IdentityError,
    authenticate,
    get_user_by_email,
    get_user_by_public_id,
    list_audit,
    logout,
    refresh,
    register,
    request_password_reset,
    reset_password,
    role_scopes,
    send_verification_email,
    verify_email,
)
from bizatlas.observability import observe
from bizatlas.observability.metrics import default_metrics
from bizatlas.service.health import liveness, readiness
from bizatlas.tools.builtins import register_default_tools
from bizatlas.tools.permissions import matrix_summary
from apps.api.auth_deps import get_principal, guard, guard_review, resolve_principal
from apps.api.observability_middleware import ObservabilityMiddleware

settings = get_settings()

app = FastAPI(title="BizAtlas API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 阶段 3：可观测中间件（请求 ID / 计数 / 耗时 / 结构化访问日志）
app.add_middleware(ObservabilityMiddleware)


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


class ReviewRequest(BaseModel):
    decision: str  # approve | reject | return
    comment: str = ""


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # 阶段 3：填充受治理工具注册表（权限+熔断+沙箱）
    register_default_tools()


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


# —— 阶段 3：高可用健康探针（liveness/readiness 分离）——
@app.get("/v1/health/live")
def health_live() -> Envelope[dict]:
    return Envelope(ok=True, data=liveness(), meta={"mode": settings.bizatlas_mode})


@app.get("/v1/health/ready")
def health_ready() -> Envelope[dict]:
    data = readiness()
    return Envelope(ok=data["status"] == "ok", data=data, meta={"mode": settings.bizatlas_mode})


@app.get("/v1/metrics")
def metrics(fmt: str = "prometheus") -> Response:
    """可观测指标：默认 Prometheus 文本格式，?fmt=json 返回结构化快照。"""
    m = default_metrics()
    if fmt == "json":
        from fastapi.responses import JSONResponse

        return JSONResponse(m.snapshot())
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(m.as_prometheus(), media_type="text/plain; version=0.0.4")


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
@observe("api.analyze")
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


@app.post("/v1/analyze/pipeline")
@observe("api.analyze_pipeline")
def analyze_pipeline(req: AnalyzeRequest) -> Envelope[dict]:
    """多 Agent 管线研判：确定性内核 + 分类/规划/研究/写作 Agent。

    返回管线完整产出，并附带可视化执行迹 trace（Agent 卡 / 工具调用 /
    事件时间线 / 证据面板），供前端「调查工作台」回放渲染。
    """
    try:
        result = run_analysis_pipeline(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    trace = build_trace(result)
    degraded = result.get("metrics_count", 0) == 0
    return Envelope(
        ok=True,
        data={**result, "trace": trace},
        meta={
            "request_id": result.get("task_id"),
            "mode": settings.bizatlas_mode,
            "pipeline_mode": result.get("pipeline_mode"),
            "degraded": degraded,
        },
    )


@app.get("/v1/analyze/pipeline/stream")
def analyze_pipeline_stream(company_id: str, task: str = "analyze_risk"):
    """多 Agent 管线实时流（SSE）：逐步推送 Agent 状态/事件，结束时附完整 trace。

    前端用 EventSource 订阅（GET，便于经 vite 代理同源）。开发态鉴权关闭，无需令牌。
    """
    import json

    from bizatlas.contracts.models import AnalyzeRequest
    from bizatlas.orchestrator.stream import stream_analysis_pipeline

    req = AnalyzeRequest(company_id=company_id, intent=task)

    def event_gen():
        try:
            for ev in stream_analysis_pipeline(req):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ===== 邮箱用户系统（身份基础设施） =====
class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str | None = None
    role: str = "viewer"  # viewer/analyst/reviewer/admin


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class RequestVerificationRequest(BaseModel):
    email: str


class PasswordResetRequestRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@app.post("/v1/auth/register")
def auth_register(req: RegisterRequest, request: Request) -> Envelope[dict]:
    """邮箱注册（默认 viewer）。重复邮箱 → 409。"""
    try:
        user = register(
            req.email,
            req.password,
            nickname=req.nickname,
            role=req.role,
            ip=_client_ip(request),
        )
    except IdentityError as exc:
        raise HTTPException(status_code=409 if "already registered" in str(exc) else 400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})


@app.post("/v1/auth/login")
def auth_login(req: LoginRequest, request: Request) -> Envelope[dict]:
    """邮箱+密码登录 → 访问/刷新令牌。失败 → 401。"""
    try:
        out = authenticate(req.email, req.password, ip=_client_ip(request))
    except IdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return Envelope(ok=True, data=out, meta={"degraded": False})


@app.post("/v1/auth/refresh")
def auth_refresh(req: RefreshRequest) -> Envelope[dict]:
    """刷新令牌换访问令牌。失败 → 401。"""
    try:
        out = refresh(req.refresh_token)
    except IdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return Envelope(ok=True, data=out, meta={"degraded": False})


@app.post("/v1/auth/logout")
def auth_logout(req: LogoutRequest) -> Envelope[dict]:
    """撤销刷新令牌会话。"""
    logout(req.refresh_token)
    return Envelope(ok=True, data={"revoked": True}, meta={"degraded": False})


@app.get("/v1/auth/me")
def auth_me(principal: Principal = Depends(resolve_principal)) -> Envelope[dict]:
    """当前登录用户（令牌真实生效；开发态无令牌退回匿名 ADMIN）。"""
    if principal.user_id in ("anonymous",):
        return Envelope(
            ok=True,
            data={
                "user": None,
                "anonymous": True,
                "role": principal.role.value,
                "scopes": sorted(s.value for s in principal.scopes),
            },
            meta={"degraded": False},
        )
    u = get_user_by_public_id(principal.user_id)
    if not u:
        return Envelope(
            ok=True,
            data={"user": None, "role": principal.role.value, "scopes": sorted(s.value for s in principal.scopes)},
            meta={"degraded": False},
        )
    return Envelope(
        ok=True,
        data={"user": u.to_public(), "role": principal.role.value, "scopes": sorted(s.value for s in principal.scopes)},
        meta={"degraded": False},
    )


@app.get("/v1/auth/rbac")
def auth_rbac_matrix() -> Envelope[dict]:
    """公开 RBAC 矩阵（角色→权限），供前端登录/权限说明。"""
    return Envelope(
        ok=True,
        data={"roles": sorted(role_scopes(r) for r in ["viewer", "analyst", "reviewer", "admin"]), "matrix": matrix_summary()},
        meta={"degraded": False},
    )


@app.get("/v1/auth/audit")
def auth_audit(
    principal: Principal = Depends(guard(Action.ADMIN)),
    limit: int = 50,
) -> Envelope[dict]:
    """审计日志（仅 ADMIN）。返回登录/改密/权限变更等事件。"""
    return Envelope(ok=True, data={"events": list_audit(limit=limit)}, meta={"degraded": False})


# ===== 邮箱验证 / 密码找回 =====
@app.post("/v1/auth/request-verification")
def auth_request_verification(req: RequestVerificationRequest, request: Request) -> Envelope[dict]:
    """（重新）发送邮箱验证邮件。邮箱不存在或已验证时静默成功（不泄露状态）。"""
    user = get_user_by_email(req.email)
    if user and not user.email_verified:
        try:
            send_verification_email(user)
        except IdentityError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"sent": True}, meta={"degraded": False})


@app.get("/v1/auth/verify-email")
def auth_verify_email(token: str) -> Envelope[dict]:
    """邮箱验证回调（前端验证页点击链接触发）。无效/过期/已用 → 400。"""
    try:
        user = verify_email(token)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})


@app.post("/v1/auth/request-password-reset")
def auth_request_password_reset(req: PasswordResetRequestRequest, request: Request) -> Envelope[dict]:
    """发起密码重置（发邮件）。邮箱不存在时静默成功（不泄露账号是否存在）。"""
    try:
        request_password_reset(req.email)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"sent": True}, meta={"degraded": False})


@app.post("/v1/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest) -> Envelope[dict]:
    """用重置 token 设置新密码。无效/过期/已用/弱密码 → 400。"""
    try:
        user = reset_password(req.token, req.new_password)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})


@app.post("/v1/reports")
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
def rules_from_nl(
    req: NlRuleRequest,
    principal: Principal = Depends(guard(Action.MANAGE_RULES)),
) -> Envelope[dict]:
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
def rules_activate(
    rule_id: str,
    confirm: bool = False,
    principal: Principal = Depends(guard(Action.MANAGE_RULES)),
) -> Envelope[dict]:
    if not confirm:
        raise HTTPException(status_code=409, detail="激活规则需要 confirm=true")
    try:
        saved = activate_rule(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(ok=True, data=saved)


@app.post("/v1/providers/akshare/fetch")
def akshare_fetch(
    req: AkshareFetchRequest,
    principal: Principal = Depends(guard(Action.TOOL_CALL)),
) -> Envelope[dict]:
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


@app.post("/v1/workflows/{workflow_id}/review")
def workflow_review(
    workflow_id: str,
    req: ReviewRequest,
    principal: Principal = Depends(guard_review()),
) -> Envelope[dict]:
    """人工复核状态机（阶段 0 内核）接入 RBAC：仅 reviewer/admin 可操作。"""
    try:
        data = review_due_diligence(
            workflow_id,
            reviewer=principal.user_id,
            decision=req.decision,
            comment=req.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(
        ok=True,
        data=data,
        meta={"reviewer": principal.user_id, "decision": req.decision},
    )


@app.get("/v1/admin/rbac")
def admin_rbac(principal: Principal = Depends(guard(Action.ADMIN))) -> Envelope[dict]:
    """管理端点（阶段 3）：查看角色-权限矩阵，需 admin 权限。"""
    return Envelope(
        ok=True,
        data={
            "matrix": matrix_summary(),
            "roles": [r.value for r in Role],
            "actions": [a.value for a in Action],
        },
        meta={"viewer": principal.user_id},
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


@app.post("/v1/rules/reload")
def rules_reload(principal: Principal = Depends(guard(Action.MANAGE_RULES))) -> Envelope[dict]:
    """规则热更新：显式重新加载全部规则并即时生效（开发态鉴权关闭时无需令牌）。

    规则加载层当前无缓存（每次读取文件+DB 最新态），此端点提供显式触发与计数，
    便于运维在修改规则文件/DB 后确认生效，亦为将来引入缓存时的统一失效入口。
    """
    loaded = load_all_rules()
    return Envelope(
        ok=True,
        data={"reloaded": len(loaded), "mode": settings.bizatlas_mode},
        meta={"degraded": False},
    )


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
