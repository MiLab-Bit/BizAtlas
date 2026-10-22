from __future__ import annotations

from bizatlas.auth.rbac import Action, Principal
from bizatlas.contracts.models import Envelope
from bizatlas.rules.nl_compiler import compile_rule_from_nl
from bizatlas.rules.store import activate_rule, load_all_rules, save_pilot_rule
from fastapi import APIRouter, Depends, HTTPException

from apps.api.app.main import (
    NlRuleRequest,
    settings,
)
from apps.api.auth_deps import guard

router = APIRouter()

@router.post("/v1/rules/from-nl")
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

@router.post("/v1/rules/{rule_id}/activate")
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

@router.get("/v1/rules")
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

@router.post("/v1/rules/reload")
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

