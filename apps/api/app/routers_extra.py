"""额外 API 路由（P1/P2 新端点，集中挂载避免改动 main.py 主干）。

挂载方式：main.py 末尾 ``app.include_router(router)``。
含：
- POST /v1/analytics/feedback         效果反馈（RaaS/采纳率前置）
- GET  /v1/analytics/feedback/summary 反馈聚合
- GET  /v1/metrics                     Prometheus 文本指标
- GET  /v1/companies/{id}/contagion    担保链违约传染推导
- GET  /v1/demo/companies              工作台演示用：4 家不同类型真实 A 股上市公司
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
from bizatlas.data.db import get_connection

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


@router.get("/v1/analytics/feedback/dashboard")
def analytics_feedback_dashboard() -> Envelope[dict]:
    """效果度量看板（RaaS/采纳率前置）：聚合反馈事件的决策分布、采纳率与近期事件。"""
    return Envelope(ok=True, data=feedback_svc.feedback_dashboard())


# ——— 工作台演示企业（4 家真实 A 股上市公司，AkShare 公开财报落库） ———
# 由 scripts/seed_demo_companies.py 播种，覆盖「优质 → 高杠杆 → 承压 → 资不抵债」
# 四类风险特征，便于主办方直观对比。指标全部来自真实公开财报，不做任何编造。
DEMO_COMPANIES = [
    {"id": "co-demo-600519", "code": "600519", "name": "贵州茅台",
     "industry": "消费/白酒", "kind": "优质低杠杆",
     "note": "高毛利、低负债、现金流充沛，作为健康对照样本"},
    {"id": "co-demo-002594", "code": "002594", "name": "比亚迪",
     "industry": "制造/新能源", "kind": "高杠杆扩张",
     "note": "负债率偏高但保持盈利，短期偿债指标偏紧"},
    {"id": "co-demo-000002", "code": "000002", "name": "万科A",
     "industry": "房地产", "kind": "承压亏损",
     "note": "行业下行，毛利率与 ROE 走弱，已连续亏损"},
    {"id": "co-demo-600340", "code": "600340", "name": "华夏幸福",
     "industry": "房地产", "kind": "资不抵债",
     "note": "资产负债率破 100%（净资产为负），连续多年亏损"},
]

# 卡片上展示的关键指标（顺序即展示顺序）
DEMO_METRIC_KEYS = ["资产负债率", "流动比率", "速动比率", "净利率", "ROE", "毛利率",
                 "连续亏损年数", "Altman_Z值"]


def _altman_zone(z):
    """原始 Altman Z-Score 标准区带（上市制造业 5 变量模型）。"""
    if z is None:
        return None
    if z > 2.99:
        return "安全区"
    if z >= 1.81:
        return "灰色区"
    return "破产区"


@router.get("/v1/demo/companies")
def demo_companies() -> Envelope[list]:
    """背调工作台演示企业：4 家真实上市公司的最新公开财报指标与当前评级。

    数据来源 AkShare 公开财报（落库时记录 source_json 与报告期，可追溯）。
    非财务维度（商誉/担保链/股权质押等）公开源无法获取，按数据缺口如实呈现。
    """
    out = []
    try:
        conn = get_connection()
        try:
            conn.row_factory = None
            for meta in DEMO_COMPANIES:
                cid = meta["id"]
                row = conn.execute(
                    "SELECT id, name, industry FROM companies WHERE id = ?", (cid,)
                ).fetchone()
                if not row:
                    continue
                metrics, period = {}, None
                for mid, mname, mval, as_of in conn.execute(
                    "SELECT id, name, value, as_of FROM financial_metrics WHERE company_id = ?",
                    (cid,),
                ):
                    if mname in DEMO_METRIC_KEYS:
                        metrics[mname] = mval
                        period = period or as_of
                grade = conn.execute(
                    "SELECT grade FROM risk_scores WHERE company_id = ? "
                    "ORDER BY rowid DESC LIMIT 1", (cid,)
                ).fetchone()
                z = metrics.get("Altman_Z值")
                out.append({
                    **meta,
                    "period": period,
                    "metrics": metrics,
                    "grade": grade[0] if grade else None,
                    "altman_z": z,
                    "altman_zone": _altman_zone(z),
                })
        finally:
            conn.close()
    except Exception as exc:  # 演示端点不因数据异常拖垮工作台
        return Envelope(ok=False, data=[], error=f"演示企业取数失败: {exc}")
    return Envelope(ok=True, data=out, meta={"count": len(out), "degraded": False})
