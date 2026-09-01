"""额外 API 路由（P1/P2 新端点，集中挂载避免改动 main.py 主干）。

挂载方式：main.py 末尾 ``app.include_router(router)``。
含：
- POST /v1/analytics/feedback         效果反馈（RaaS/采纳率前置）
- GET  /v1/analytics/feedback/summary 反馈聚合
- GET  /v1/metrics                     Prometheus 文本指标
- GET  /v1/companies/{id}/contagion    担保链违约传染推导
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from bizatlas.config import get_settings
from bizatlas.contracts.models import Envelope
from bizatlas.kg.contagion import compute_contagion
from bizatlas.observability.metrics import default_metrics
from apps.api.auth_deps import get_principal
from bizatlas.analytics import feedback as feedback_svc

router = APIRouter()


class FeedbackBody(BaseModel):
    report_id: Optional[str] = None
    company_id: Optional[str] = None
    action: str = Field(..., description="report_accepted|report_overridden|decision_accepted|decision_overridden|review_approve|review_reject|review_return")
    decision: Optional[str] = None
    comment: Optional[str] = None
    latency_ms: Optional[float] = None


@router.post("/v1/analytics/feedback")
def analytics_feedback(req: FeedbackBody, principal=Depends(get_principal)) -> Envelope[dict]:
    """记录一次效果反馈（研判/决策被采纳或推翻）。"""
    try:
        rec = feedback_svc.record_feedback(
            report_id=req.report_id,
            company_id=req.company_id,
            analyst=getattr(principal, "user_id", None),
            action=req.action,
            decision=req.decision,
            comment=req.comment,
            latency_ms=req.latency_ms,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(ok=True, data=rec, meta={"degraded": False})


@router.get("/v1/analytics/feedback/summary")
def analytics_feedback_summary() -> Envelope[dict]:
    return Envelope(ok=True, data=feedback_svc.feedback_summary())


@router.get("/v1/metrics")
def metrics_prometheus() -> PlainTextResponse:
    """Prometheus 文本 exposition（供 Prometheus 抓取）。"""
    text = default_metrics().as_prometheus()
    return PlainTextResponse(text or "# no metrics yet\n", media_type="text/plain; version=0.0.4")


@router.get("/v1/companies/{company_id}/contagion")
def company_contagion(company_id: str, fixture_id: Optional[str] = None) -> Envelope[dict]:
    """担保链违约传染推导（P1）。

    若 company_id 为 healthy/risky/defaulted 演示主体，自动取对应 fixture 图谱。
    """
    fid = fixture_id
    if company_id in {"healthy", "risky", "defaulted"}:
        fid = company_id
    data = compute_contagion(company_id, fixture_id=fid)
    return Envelope(ok=True, data=data, meta={"degraded": False})
