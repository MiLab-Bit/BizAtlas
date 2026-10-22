from __future__ import annotations

from bizatlas.auth.rbac import Principal
from bizatlas.contracts.models import Envelope
from bizatlas.data import repo
from bizatlas.workflow.due_diligence import (
    advance_due_diligence,
    get_due_diligence,
    review_due_diligence,
    start_due_diligence,
)
from fastapi import APIRouter, Depends, HTTPException

from apps.api.app.main import (
    AdvanceWorkflowRequest,
    ReviewRequest,
    StartWorkflowRequest,
    settings,
)
from apps.api.auth_deps import guard_review

router = APIRouter()

@router.post("/v1/workflows/due-diligence")
async def start_workflow(req: StartWorkflowRequest) -> Envelope[dict]:
    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import start_due_diligence_wf

        try:
            data = await start_due_diligence_wf(req.model_dump())
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Envelope(ok=True, data=data, meta={"engine": "temporal"})
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

@router.get("/v1/workflows")
def workflows() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_workflows())

@router.get("/v1/workflows/{workflow_id}")
async def workflow_detail(workflow_id: str) -> Envelope[dict]:
    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import get_due_diligence_wf

        try:
            data = await get_due_diligence_wf(workflow_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Envelope(ok=True, data=data, meta={"engine": "temporal"})
    try:
        data = get_due_diligence(workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)

@router.post("/v1/workflows/{workflow_id}/advance")
async def workflow_advance(workflow_id: str, req: AdvanceWorkflowRequest) -> Envelope[dict]:
    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import advance_due_diligence_wf

        try:
            data = await advance_due_diligence_wf(
                workflow_id, action=req.action, confirm=req.confirm, manual_flags=req.manual_flags
            )
        except Exception as exc:  # noqa: BLE001
            status = 409 if "confirm" in str(exc) or "齐套" in str(exc) or "先" in str(exc) else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        return Envelope(
            ok=True,
            data=data,
            meta={"action": req.action, "human_gate": req.action == "submit", "engine": "temporal"},
        )
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

@router.post("/v1/workflows/{workflow_id}/review")
async def workflow_review(
    workflow_id: str,
    req: ReviewRequest,
    principal: Principal = Depends(guard_review()),
) -> Envelope[dict]:
    """人工复核状态机（阶段 0 内核）接入 RBAC：仅 reviewer/admin 可操作。"""
    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import review_due_diligence_wf

        try:
            data = await review_due_diligence_wf(
                workflow_id,
                decision=req.decision,
                comment=req.comment,
                reviewer=principal.user_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Envelope(
            ok=True,
            data=data,
            meta={"reviewer": principal.user_id, "decision": req.decision, "engine": "temporal"},
        )
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

