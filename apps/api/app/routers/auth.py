from __future__ import annotations

import time

from bizatlas.auth.rbac import Action, Principal
from bizatlas.contracts.models import Envelope
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
from bizatlas.identity import model_providers as mp_store
from bizatlas.identity.apikeys import (
    create_api_key,
    generate_api_key,
    list_api_keys,
    revoke_api_key,
    rotate_api_key,
)
from bizatlas.identity.crypto import PROVIDER_PRESETS
from bizatlas.tools.permissions import matrix_summary
from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.app.main import (
    ApiKeyCreateRequest,
    ApiKeyRevokeRequest,
    ApiKeyRotateRequest,
    LoginRequest,
    LogoutRequest,
    ModelProviderCreateRequest,
    ModelProviderTestRequest,
    PasswordResetRequestRequest,
    RefreshRequest,
    RegisterRequest,
    RequestVerificationRequest,
    ResetPasswordRequest,
    _mp_preset_base,
    _mp_preset_model,
    _test_provider,
)
from apps.api.auth_deps import get_principal, guard, resolve_principal
from apps.api.rate_limit import (
    LOGIN_LIMIT,
    PW_RESET_LIMIT,
    REGISTER_LIMIT,
    RESET_PW_LIMIT,
    rate_limit_identity,
    rate_limit_ip,
)
from apps.api.rate_limit import get_client_ip as _client_ip

router = APIRouter()

@router.post("/v1/auth/register")
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

@router.post("/v1/auth/login")
def auth_login(req: LoginRequest, request: Request) -> Envelope[dict]:
    """邮箱+密码登录 → 访问/刷新令牌。失败 → 401。"""
    # P1-2：登录限速（10 次/分/IP），防爆破
    rate_limit_ip(request, "login", *LOGIN_LIMIT)
    try:
        out = authenticate(req.email, req.password, ip=_client_ip(request))
    except IdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return Envelope(ok=True, data=out, meta={"degraded": False})

@router.post("/v1/auth/refresh")
def auth_refresh(req: RefreshRequest) -> Envelope[dict]:
    """刷新令牌换访问令牌。失败 → 401。"""
    try:
        out = refresh(req.refresh_token)
    except IdentityError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return Envelope(ok=True, data=out, meta={"degraded": False})

@router.post("/v1/auth/logout")
def auth_logout(req: LogoutRequest) -> Envelope[dict]:
    """撤销刷新令牌会话。"""
    logout(req.refresh_token)
    return Envelope(ok=True, data={"revoked": True}, meta={"degraded": False})

@router.get("/v1/auth/me")
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

@router.get("/v1/auth/rbac")
def auth_rbac_matrix() -> Envelope[dict]:
    """公开 RBAC 矩阵（角色→权限），供前端登录/权限说明。"""
    return Envelope(
        ok=True,
        data={"roles": sorted(role_scopes(r) for r in ["viewer", "analyst", "reviewer", "admin"]), "matrix": matrix_summary()},
        meta={"degraded": False},
    )

@router.get("/v1/auth/audit")
def auth_audit(
    principal: Principal = Depends(guard(Action.ADMIN)),
    limit: int = 50,
) -> Envelope[dict]:
    """审计日志（仅 ADMIN）。返回登录/改密/权限变更等事件。"""
    return Envelope(ok=True, data={"events": list_audit(limit=limit)}, meta={"degraded": False})

@router.post("/v1/auth/request-verification")
def auth_request_verification(req: RequestVerificationRequest, request: Request) -> Envelope[dict]:
    """（重新）发送邮箱验证邮件。邮箱不存在或已验证时静默成功（不泄露状态）。"""
    user = get_user_by_email(req.email)
    if user and not user.email_verified:
        try:
            send_verification_email(user)
        except IdentityError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"sent": True}, meta={"degraded": False})

@router.get("/v1/auth/verify-email")
def auth_verify_email(token: str) -> Envelope[dict]:
    """邮箱验证回调（前端验证页点击链接触发）。无效/过期/已用 → 400。"""
    try:
        user = verify_email(token)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})

@router.post("/v1/auth/request-password-reset")
def auth_request_password_reset(req: PasswordResetRequestRequest, request: Request) -> Envelope[dict]:
    """发起密码重置（发邮件）。邮箱不存在时静默成功（不泄露账号是否存在）。"""
    # P1-2：密码重置请求限速（5 次/时/邮箱），防邮箱轰炸
    rate_limit_identity(req.email, "pwreset", *PW_RESET_LIMIT)
    try:
        request_password_reset(req.email)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"sent": True}, meta={"degraded": False})

@router.post("/v1/auth/reset-password")
def auth_reset_password(req: ResetPasswordRequest, request: Request) -> Envelope[dict]:
    """用重置 token 设置新密码。无效/过期/已用/弱密码 → 400。"""
    # P1-2：用 token 重置密码限速（10 次/分/IP），防 token 爆破
    rate_limit_ip(request, "resetpw", *RESET_PW_LIMIT)
    try:
        user = reset_password(req.token, req.new_password)
    except IdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Envelope(ok=True, data={"user": user.to_public()}, meta={"degraded": False})

@router.post("/v1/auth/apikeys")
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

@router.get("/v1/auth/apikeys")
def auth_list_apikeys(principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    """列出当前账号的 API Key（掩码，不含明文）。"""
    return Envelope(ok=True, data={"keys": list_api_keys(principal.user_id)}, meta={"degraded": False})

@router.post("/v1/auth/apikeys/rotate")
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

@router.post("/v1/auth/apikeys/revoke")
def auth_revoke_apikey(
    req: ApiKeyRevokeRequest, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """撤销指定 Key（立即失效）。"""
    if not revoke_api_key(req.key_id, principal.user_id):
        raise HTTPException(status_code=404, detail="key not found")
    return Envelope(ok=True, data={"revoked": req.key_id}, meta={"degraded": False})

@router.get("/v1/auth/model-providers/presets")
def auth_model_provider_presets() -> Envelope[dict]:
    """公开供应商预设（不含任何密钥）。"""
    return Envelope(ok=True, data={"providers": PROVIDER_PRESETS}, meta={"degraded": False})

@router.get("/v1/auth/model-providers")
def auth_list_model_providers(principal: Principal = Depends(get_principal)) -> Envelope[dict]:
    """列出当前账号的模型配置（不含明文密钥）。"""
    return Envelope(
        ok=True,
        data={"providers": mp_store.list_model_providers(principal.user_id)},
        meta={"degraded": False},
    )

@router.post("/v1/auth/model-providers/test")
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

@router.post("/v1/auth/model-providers")
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

@router.delete("/v1/auth/model-providers/{pid}")
def auth_delete_model_provider(
    pid: str, principal: Principal = Depends(get_principal)
) -> Envelope[dict]:
    """删除一条模型配置。"""
    if not mp_store.delete_model_provider(pid, principal.user_id):
        raise HTTPException(status_code=404, detail="配置不存在")
    return Envelope(ok=True, data={"deleted": pid}, meta={"degraded": False})

