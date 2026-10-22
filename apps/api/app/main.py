from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from bizatlas.config import get_settings
from bizatlas.data.db import init_db
from bizatlas.identity.crypto import PROVIDER_PRESETS
from bizatlas.tools.builtins import register_default_tools
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apps.api.audit_middleware import AuditMiddleware
from apps.api.observability_middleware import ObservabilityMiddleware

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


# —— 阶段 3：高可用健康探针（liveness/readiness 分离）——


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


# ===== 邮箱验证 / 密码找回 =====


# ===== 一次性首管理员引导（P0-1 配套：堵公开注册后仍需有建 admin 的合法通道）=====
class AdminBootstrapRequest(BaseModel):
    email: str
    password: str
    token: str
    nickname: str | None = None


# ===== Agent API Key（机器凭证）=====


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


def _sse(event: dict) -> str:
    """把事件 dict 格式化为一行 SSE（data: <json>\\n\\n）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# Optional quick create+upload helper for demos


# —— M1 安全：全局鉴权强制（非公开 /v1/* 必须携带有效 Bearer 令牌）——
from bizatlas.auth.rbac import TokenInvalid, verify_token
from bizatlas.config import get_settings
from bizatlas.identity import apikeys as _apikeys
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_PUBLIC_PATHS = {
    "/v1/auth/register", "/v1/auth/login", "/v1/auth/refresh",
    "/v1/auth/logout", "/v1/auth/verify-email", "/v1/auth/request-verification",
    "/v1/auth/request-password-reset", "/v1/auth/reset-password",
    "/v1/auth/me", "/v1/auth/rbac",
    "/v1/auth/model-providers/presets",
    "/v1/admin/bootstrap",  # 一次性首 admin 引导，自身校验 token，无 admin 时才可用
    "/v1/health", "/v1/health/live", "/v1/health/ready",
    "/v1/metrics",
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

app.add_middleware(AuditMiddleware)

app.add_middleware(AuthEnforcementMiddleware)

# ── 路由拆分（2026-10）：按域挂载，处理器见 app/routers/ ──
from apps.api.app.routers import (  # noqa: E402
    admin,
    analyze,
    auth,
    chat,
    companies,
    providers,
    reports,
    risk,
    rules,
    system,
    workflows,
)

app.include_router(admin.router)
app.include_router(analyze.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(companies.router)
app.include_router(providers.router)
app.include_router(reports.router)
app.include_router(risk.router)
app.include_router(rules.router)
app.include_router(system.router)
app.include_router(workflows.router)

from apps.api.app.routers_extra import router as _extra_router

app.include_router(_extra_router)
