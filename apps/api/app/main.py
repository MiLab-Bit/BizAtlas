from __future__ import annotations

import hashlib
import hmac
import httpx
import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from bizatlas.config import get_settings
from bizatlas.contracts.models import AnalyzeRequest, Envelope, HealthData
from bizatlas.data import repo
from bizatlas.data.db import init_db, get_connection
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
from bizatlas.identity.apikeys import (
    create_api_key,
    generate_api_key,
    list_api_keys,
    revoke_api_key,
    rotate_api_key,
)
from bizatlas.identity import model_providers as mp_store
from bizatlas.llm.client import set_request_provider
from bizatlas.identity.crypto import PROVIDER_PRESETS
from bizatlas.observability import observe
from bizatlas.observability.metrics import default_metrics
from bizatlas.service.health import liveness, readiness
from bizatlas.tools.builtins import register_default_tools
from bizatlas.tools.permissions import matrix_summary
from apps.api.auth_deps import get_principal, guard, guard_review, resolve_principal
from apps.api.observability_middleware import ObservabilityMiddleware
from apps.api.rate_limit import (
    get_client_ip as _client_ip,
    rate_limit_identity,
    rate_limit_ip,
    LOGIN_LIMIT,
    REGISTER_LIMIT,
    PW_RESET_LIMIT,
    RESET_PW_LIMIT,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 阶段 3：启动初始化（替代已废弃的 @app.on_event("startup")）
    init_db()
    register_default_tools()
    # Phase C：.env → platform LLM seed + 合规对账自检（缺口只告警）
    try:
        from bizatlas.bootstrap import run_startup_bootstrap

        boot = run_startup_bootstrap()
        app.state.bootstrap = boot
    except Exception as exc:  # noqa: BLE001
        app.state.bootstrap = {"error": str(exc)}
    yield


app = FastAPI(title="BizAtlas API", version="0.3.0", lifespan=lifespan)
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


@app.get("/v1/healthz")
def healthz() -> dict:
    # liveness 探针：不查 DB/外部依赖，供 k8s/systemd 存活检测（公开，见 _PUBLIC_PATHS）。
    return {"status": "ok", "service": "bizatlas", "version": app.version, "time": time.time()}


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


# —— P1-3：上传大小/类型限制（应用层收口到 10MB + 扩展名白名单 + 魔数校验）——
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ALLOWED_UPLOAD_EXT = {".csv", ".json", ".xlsx"}


async def _validate_upload(file: UploadFile, request: Request) -> bytes:
    # 1) 先按 Content-Length 拦（nginx 已放行 100m，此处收口 10MB）
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 10MB)")
    name = (file.filename or "").lower()
    ext = os.path.splitext(name)[1]
    if ext not in _ALLOWED_UPLOAD_EXT:
        raise HTTPException(status_code=400, detail=f"unsupported file type: {ext or 'none'} (allowed: .csv/.json/.xlsx)")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 10MB)")
    # 2) 魔数/首字节校验，防扩展名伪装
    if ext == ".xlsx" and content[:4] != b"PK\x03\x04":
        raise HTTPException(status_code=400, detail="invalid xlsx file (bad magic)")
    if ext == ".json" and content.lstrip()[:1] not in (b"{", b"["):
        raise HTTPException(status_code=400, detail="invalid json file")
    if ext == ".csv":
        head = content[:4]
        if head in (b"MZ\x90\x00", b"PK\x03\x04", b"\x7fELF"):
            raise HTTPException(status_code=400, detail="invalid csv file (binary detected)")
    return content


@app.post("/v1/companies/{company_id}/documents")
async def upload_document(
    company_id: str,
    file: UploadFile = File(...),
    request: Request = None,
) -> Envelope[dict]:
    if not repo.get_company(company_id):
        raise HTTPException(status_code=404, detail="company not found")
    content = await _validate_upload(file, request)
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
def analyze_pipeline_stream(
    company_id: str,
    task: str = "analyze_risk",
    fast: bool = False,
):
    """多 Agent 管线实时流（SSE）：逐步推送 Agent 状态/事件，结束时附完整 trace。

    前端用 EventSource 订阅（GET，便于经 vite 代理同源）。开发态鉴权关闭，无需令牌。
    P1-4：用后台线程驱动管线、队列取事件，空闲 15s 发送 SSE 注释心跳 ": ping"，
    防止 nginx/cloudflared 等长连接因空闲被中间层掐断。

    fast=true：评分内核跳过 LLM 润色，优先出 grade/score（演示控延迟）。
    """
    import json

    from bizatlas.contracts.models import AnalyzeRequest
    from bizatlas.orchestrator.stream import stream_analysis_pipeline

    req = AnalyzeRequest(
        company_id=company_id,
        intent=task,
        options={"skip_polish": fast, "fast": fast, "include_stress": not fast},
    )

    def event_gen():
        q: "queue.Queue[tuple]" = queue.Queue()

        def _run() -> None:
            try:
                for ev in stream_analysis_pipeline(req):
                    q.put(("data", ev))
            except Exception as exc:  # noqa: BLE001
                q.put(("error", str(exc)))
            finally:
                q.put(("end", None))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        while True:
            try:
                kind, payload = q.get(timeout=15)
            except queue.Empty:
                # 空闲心跳：浏览器 EventSource 自动忽略注释行
                yield ": ping\n\n"
                continue
            if kind == "data":
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps({'message': payload}, ensure_ascii=False)}\n\n"
            else:  # end
                yield "event: end\ndata: {}\n\n"
                break

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
    # P0-1：公开注册强制为 viewer，忽略客户端提交的 role（含 admin）。
    # 提权仅允许已有管理员后续操作（见 /v1/admin/bootstrap 一次性建首 admin）。
    role: Literal["viewer"] = "viewer"


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


class ApiKeyCreateRequest(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None


class ApiKeyRotateRequest(BaseModel):
    key_id: str


class ApiKeyRevokeRequest(BaseModel):
    key_id: str


@app.post("/v1/auth/register")
def auth_register(req: RegisterRequest, request: Request) -> Envelope[dict]:
    """邮箱注册（强制 viewer，P0-1 修复：忽略客户端 role）。重复邮箱 → 409。"""
    # P1-2：公开注册限速（5 次/分/IP）
    rate_limit_ip(request, "register", *REGISTER_LIMIT)
    try:
        user = register(
            req.email,
            req.password,
            nickname=req.nickname,
            role="viewer",
            ip=_client_ip(request),
        )
    except IdentityError as exc:
        raise HTTPException(status_code=409 if "already registered" in str(exc) else 400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})


@app.post("/v1/auth/login")
def auth_login(req: LoginRequest, request: Request) -> Envelope[dict]:
    """邮箱+密码登录 → 访问/刷新令牌。失败 → 401。"""
    # P1-2：登录限速（10 次/分/IP），防爆破
    rate_limit_ip(request, "login", *LOGIN_LIMIT)
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
    # P1-2：密码重置请求限速（5 次/时/邮箱），防邮箱轰炸
    rate_limit_identity(req.email, "pwreset", *PW_RESET_LIMIT)
    try:
        request_password_reset(req.email)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"sent": True}, meta={"degraded": False})


@app.post("/v1/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest, request: Request) -> Envelope[dict]:
    """用重置 token 设置新密码。无效/过期/已用/弱密码 → 400。"""
    # P1-2：用 token 重置密码限速（10 次/分/IP），防 token 爆破
    rate_limit_ip(request, "resetpw", *RESET_PW_LIMIT)
    try:
        user = reset_password(req.token, req.new_password)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})


# ===== 一次性首管理员引导（P0-1 配套：堵公开注册后仍需有建 admin 的合法通道）=====
class AdminBootstrapRequest(BaseModel):
    email: str
    password: str
    token: str
    nickname: str | None = None


@app.post("/v1/admin/bootstrap")
def admin_bootstrap(req: AdminBootstrapRequest, request: Request) -> Envelope[dict]:
    """一次性创建/提升首个管理员。仅当系统尚无 admin 时可用，受 BIZATLAS_BOOTSTRAP_TOKEN 保护。

    - 邮箱已存在（非 admin）：直接提升为 admin（并标记邮箱已验证）。
    - 邮箱不存在：以 admin 角色新建（并强制邮箱已验证，便于立即登录）。
    - 已有 admin：返回 409（引导端点自锁，防滥用）。
    """
    settings = get_settings()
    bt = settings.bizatlas_bootstrap_token
    if not bt or not hmac.compare_digest(req.token, bt):
        raise HTTPException(status_code=401, detail="invalid bootstrap token")
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            raise HTTPException(status_code=409, detail="admin already exists; bootstrap disabled")
    finally:
        conn.close()

    email = (req.email or "").strip().lower()
    ip = _client_ip(request)
    existing = get_user_by_email(email)
    now_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    if existing:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET role='admin', email_verified=1, updated_at=? WHERE id=?",
                (now_iso, existing.id),
            )
            conn.commit()
        finally:
            conn.close()
        user = get_user_by_public_id(existing.public_id)
        promoted = True
    else:
        if len(req.password or "") < 8:
            raise HTTPException(status_code=400, detail="password too short (min 8)")
        user = register(email, req.password, nickname=req.nickname, role="admin", ip=ip)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET email_verified=1, updated_at=? WHERE email=?",
                (now_iso, email),
            )
            conn.commit()
        finally:
            conn.close()
        user = get_user_by_email(email)
        promoted = False
    return Envelope(
        ok=True,
        data={"user": user.to_public(), "promoted": promoted},
        meta={"degraded": False},
    )


# ===== Agent API Key（机器凭证）=====
@app.post("/v1/auth/apikeys")
def auth_create_apikey(
    req: ApiKeyCreateRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """为当前账号创建一个 Agent API Key（明文仅返回一次）。

    P2-7：scopes 字段存库备用（前向兼容），但当前权限实际按 owner 角色收口
    （apikeys.principal_for_owner 用 ROLE_SCOPES[role]），scopes 不参与鉴权决策。
    """
    name = (req.name or "unnamed").strip() or "unnamed"
    scopes = req.scopes or ["*"]
    plain, prefix, h = generate_api_key("ba_")
    kid = create_api_key(principal.user_id, name, h, prefix, scopes)
    return Envelope(
        ok=True,
        data={"key_id": kid, "key": plain, "preview": f"{prefix}****",
              "warning": "此明文 Key 仅显示一次，请妥善保存。"},
        meta={"degraded": False},
    )


@app.get("/v1/auth/apikeys")
def auth_list_apikeys(principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    """列出当前账号的 API Key（掩码，不含明文）。"""
    return Envelope(ok=True, data={"keys": list_api_keys(principal.user_id)}, meta={"degraded": False})


@app.post("/v1/auth/apikeys/rotate")
def auth_rotate_apikey(
    req: ApiKeyRotateRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """轮换指定 Key：旧 Key 立即失效，返回新明文（仅一次）。"""
    plain, prefix, h = generate_api_key("ba_")
    if not rotate_api_key(req.key_id, principal.user_id, h, prefix):
        raise HTTPException(status_code=404, detail="key not found")
    return Envelope(
        ok=True,
        data={"key_id": req.key_id, "key": plain, "warning": "旧 Key 已失效，此为新 Key（仅显示一次）。"},
        meta={"degraded": False},
    )


@app.post("/v1/auth/apikeys/revoke")
def auth_revoke_apikey(
    req: ApiKeyRevokeRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """撤销指定 Key（立即失效）。"""
    if not revoke_api_key(req.key_id, principal.user_id):
        raise HTTPException(status_code=404, detail="key not found")
    return Envelope(ok=True, data={"revoked": req.key_id}, meta={"degraded": False})


# ===== 模型配置（用户自带大模型供应商密钥）=====
class ModelProviderCreateRequest(BaseModel):
    name: str
    provider: str
    apiKey: str
    baseUrl: str | None = None
    model: str | None = None
    slot: str = "text"  # 'text'（文本模型）或 'multimodal'（多模态模型）


class ModelProviderTestRequest(BaseModel):
    provider: str
    apiKey: str
    baseUrl: str | None = None
    model: str | None = None


def _mp_preset_base(provider: str) -> str:
    for pr in PROVIDER_PRESETS:
        if pr["provider"] == provider:
            return pr["baseUrl"]
    return ""


def _mp_preset_model(provider: str) -> str:
    for pr in PROVIDER_PRESETS:
        if pr["provider"] == provider:
            return pr["defaultModel"]
    return ""


def _test_provider(api_key: str, base_url: str, model: str) -> dict:
    """直连供应商做一次最小 chat 调用，验证 key 可用。"""
    base = (base_url or "").rstrip("/")
    if not base:
        return {"ok": False, "latency_ms": 0, "error": "自定义供应商需填写 Base URL"}
    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model or "gpt-4o-mini",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 4,
        "temperature": 0,
    }
    t0 = time.time()
    try:
        with httpx.Client(timeout=20.0) as cli:
            r = cli.post(url, headers=headers, json=payload)
        latency = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return {"ok": True, "latency_ms": latency, "model": model or "gpt-4o-mini"}
        detail = r.text[:300]
        try:
            detail = r.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        return {"ok": False, "latency_ms": latency, "error": f"HTTP {r.status_code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency, "error": str(exc)[:300]}


@app.get("/v1/auth/model-providers/presets")
def auth_model_provider_presets() -> Envelope[dict]:
    """公开供应商预设（不含任何密钥）。"""
    return Envelope(ok=True, data={"providers": PROVIDER_PRESETS}, meta={"degraded": False})


@app.get("/v1/auth/model-providers")
def auth_list_model_providers(principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    """列出当前账号的模型配置（不含明文密钥）。"""
    return Envelope(
        ok=True,
        data={"providers": mp_store.list_model_providers(principal.user_id)},
        meta={"degraded": False},
    )


@app.post("/v1/auth/model-providers/test")
def auth_test_model_provider(
    req: ModelProviderTestRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """用用户填写的密钥直连供应商验证可用性（不落库）。"""
    res = _test_provider(
        req.apiKey,
        req.baseUrl or _mp_preset_base(req.provider),
        req.model or _mp_preset_model(req.provider),
    )
    return Envelope(ok=True, data=res, meta={"degraded": False})


@app.post("/v1/auth/model-providers")
def auth_create_model_provider(
    req: ModelProviderCreateRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """保存一条模型配置：保存前先直连供应商验证密钥可用性，并标记状态。"""
    if not req.name or not req.provider or not req.apiKey:
        raise HTTPException(status_code=400, detail="名称、供应商、密钥均为必填")
    slot = (req.slot or "text").strip()
    if slot not in ("text", "multimodal"):
        raise HTTPException(status_code=400, detail="slot 仅支持 text / multimodal")
    test = _test_provider(
        req.apiKey,
        req.baseUrl or _mp_preset_base(req.provider),
        req.model or _mp_preset_model(req.provider),
    )
    status = "active" if test["ok"] else "error"
    pid = mp_store.create_model_provider(
        principal.user_id, req.name, req.provider, req.apiKey, req.baseUrl, req.model,
        slot=slot,
    )
    mp_store.update_status(
        pid, principal.user_id, status,
        (test.get("error") if not test["ok"] else None),
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    )
    rec = mp_store.get_model_provider(pid, principal.user_id)
    rec.pop("api_key_enc", None)
    return Envelope(
        ok=True,
        data={"provider": rec, "test": test},
        meta={"degraded": False},
    )


@app.delete("/v1/auth/model-providers/{pid}")
def auth_delete_model_provider(
    pid: str, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """删除一条模型配置。"""
    if not mp_store.delete_model_provider(pid, principal.user_id):
        raise HTTPException(status_code=404, detail="配置不存在")
    return Envelope(ok=True, data={"deleted": pid}, meta={"degraded": False})


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
def chat(req: ChatRequest, principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    from bizatlas.llm.agent import handle_agent_message

    # 注入用户自带 provider（若有 active 配置），否则回退平台设置。
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    set_request_provider(
        {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    )
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
    finally:
        set_request_provider(None)
    return Envelope(ok=True, data=result)


def _sse(event: dict) -> str:
    """把事件 dict 格式化为一行 SSE（data: <json>\\n\\n）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/stream")
def chat_stream(req: ChatRequest, principal: Principal = Depends(get_principal)) -> StreamingResponse:
    """流式版 /v1/chat（SSE）。

    - ask_doc/unknown 意图：逐 token 流式输出 RAG 回答（后端 /v1/chat 保持非流式不变）。
    - 其它意图：在路由线程内同步算出完整结果，整段以单个 SSE 事件发出（保持兼容）。
    流式路径显式透传用户 active provider，不依赖跨线程 ContextVar。
    """
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    provider_dict = {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    set_request_provider(provider_dict)
    message = req.message.strip()
    try:
        from bizatlas.llm.intent import classify_intent

        intent = classify_intent(message).get("intent")
        if intent in (None, "ask_doc", "unknown"):
            from bizatlas.rag.simple import stream_ask_company

            def _gen() -> Any:
                try:
                    for ev in stream_ask_company(
                        message,
                        company_id=req.company_id,
                        fixture_id=req.fixture_id,
                        provider=provider_dict,
                    ):
                        yield _sse(ev)
                finally:
                    set_request_provider(None)

            return StreamingResponse(_gen(), media_type="text/event-stream")

        # 非流式意图：在路由线程内同步计算（ContextVar 对本线程有效），整段发出
        from bizatlas.llm.agent import handle_agent_message

        result = handle_agent_message(
            message,
            company_id=req.company_id,
            fixture_id=req.fixture_id,
            context=req.context,
        )

        def _gen() -> Any:
            try:
                yield _sse({"type": "result", "data": result})
            finally:
                set_request_provider(None)

        return StreamingResponse(_gen(), media_type="text/event-stream")
    except Exception as exc:  # noqa: BLE001
        set_request_provider(None)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
def background_chat(req: BackgroundChatRequest, principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    from bizatlas.llm.background import background_reply

    # 注入用户自带 provider（若有 active 配置），否则回退平台设置。
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    set_request_provider(
        {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    )
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
    finally:
        set_request_provider(None)
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
    request: Request = None,
) -> Envelope[dict]:
    company = repo.create_company(name, industry)
    content = await _validate_upload(file, request)
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


# —— M1 安全：全局鉴权强制（非公开 /v1/* 必须携带有效 Bearer 令牌）——
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from bizatlas.auth.rbac import TokenInvalid, verify_token
from bizatlas.config import get_settings
from bizatlas.identity import apikeys as _apikeys

_PUBLIC_PATHS = {
    "/v1/auth/register", "/v1/auth/login", "/v1/auth/refresh",
    "/v1/auth/logout", "/v1/auth/verify-email", "/v1/auth/request-verification",
    "/v1/auth/request-password-reset", "/v1/auth/reset-password",
    "/v1/auth/me", "/v1/auth/rbac",
    "/v1/auth/model-providers/presets",
    "/v1/admin/bootstrap",  # 一次性首 admin 引导，自身校验 token，无 admin 时才可用
    "/v1/healthz",
}

class AuthEnforcementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith("/v1/") or path in _PUBLIC_PATHS:
            return await call_next(request)
        settings = get_settings()
        if settings.bizatlas_auth_disabled or not settings.bizatlas_auth_secret:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"error": "UNAUTHENTICATED", "message": "Missing Bearer token"})
        token = auth[len("Bearer "):].strip()
        # 1) Agent API Key（机器凭证）：哈希命中且 active 即放行，具体权限由端点依赖再判
        rec = _apikeys.get_api_key_by_hash(hashlib.sha256(token.encode("utf-8")).hexdigest())
        if rec and rec["status"] == "active":
            _apikeys.touch_api_key(rec["id"])
            return await call_next(request)
        # 2) 人工 JWT
        try:
            verify_token(token, settings.bizatlas_auth_secret)
        except TokenInvalid:
            return JSONResponse(status_code=401, content={"error": "UNAUTHENTICATED", "message": "Invalid or expired token"})
        return await call_next(request)

app.add_middleware(AuthEnforcementMiddleware)


# ==================================================================
# 贷前审批场景聚焦 · 授信准入决策 / 评分有效性验证 / 数据授权与合规
# ==================================================================


class CreditDecisionRequest(BaseModel):
    """贷前授信准入决策请求。"""

    company_id: str
    applied_amount: float | None = Field(
        default=None, description="申请额度（万元）。缺省时仅返回额度系数区间，不给绝对金额"
    )
    tenor_months: int | None = Field(default=None, description="申请期限（月）")
    product: str = Field(default="流动资金贷款", description="授信产品名")
    include_stress: bool = Field(default=False, description="是否附带压力测试（贷前默认关，控延迟）")
    skip_polish: bool = Field(
        default=True,
        description="跳过 LLM 润色。决策数字本就不经 LLM，默认开启快路径",
    )


@app.post("/v1/credit/decision")
@observe("api.credit_decision")
def credit_decision(req: CreditDecisionRequest) -> Envelope[dict]:
    """贷前授信准入决策。

    把通用风险研判收敛为贷前审批场景下的一个具体决策动作：
    是否准入、以什么条件准入、建议额度区间、是否必须转人工终审。

    决策档位与额度系数全部由确定性规则计算，不经过大模型；
    ORANGE 及以上评级、命中一票否决、担保链含失信主体、核心数据不足
    ——以上任一情形均强制转人工终审。
    """
    from bizatlas.credit.decision import build_credit_decision

    analyze_req = AnalyzeRequest(
        company_id=req.company_id,
        intent="analyze_risk",
        options={
            "include_stress": req.include_stress,
            "include_kg": True,
            "skip_polish": req.skip_polish,
            "fast": req.skip_polish,
        },
    )
    try:
        result = run_analyze(analyze_req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    decision = build_credit_decision(
        result,
        applied_amount=req.applied_amount,
        tenor_months=req.tenor_months,
        product=req.product,
    )
    return Envelope(
        ok=True,
        data={"decision": decision, "analysis": result},
        meta={
            "scenario": "pre_lending_credit_admission",
            "manual_gate_required": decision["manual_gate"]["required"],
            "llm_used_for_numbers": False,
            "fast_path": bool(req.skip_polish),
            "mode": settings.bizatlas_mode,
        },
    )


@app.get("/v1/validation/backtest")
def validation_backtest() -> Envelope[dict]:
    """风险评分有效性回溯验证报告。

    报告未生成时返回 available=false 并说明原因，不返回任何占位数字。
    """
    from bizatlas.validation.report import load_backtest_report

    data = load_backtest_report()
    return Envelope(
        ok=True,
        data=data,
        meta={"available": bool(data.get("available"))},
    )


@app.get("/v1/compliance/statement")
def compliance_statement() -> Envelope[dict]:
    """数据授权与合规机制声明（含运行时数据源对账）。"""
    from bizatlas.compliance.statement import load_compliance_statement

    data = load_compliance_statement()
    rec = data.get("reconciliation") or {}
    return Envelope(
        ok=True,
        data=data,
        meta={
            "available": bool(data.get("available")),
            "source_count": data.get("source_count", 0),
            "declaration_consistent": rec.get("consistent"),
        },
    )
