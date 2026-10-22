from __future__ import annotations

from bizatlas.auth.rbac import Action, Principal
from bizatlas.contracts.models import DataTier, Envelope, MetricSource, MetricValue
from bizatlas.data import repo
from bizatlas.data.providers_akshare import fetch_stock_basic_metrics
from fastapi import APIRouter, Depends, HTTPException

from apps.api.app.main import (
    AkshareFetchRequest,
)
from apps.api.auth_deps import guard

router = APIRouter()

@router.post("/v1/providers/akshare/fetch")
def akshare_fetch(
    req: AkshareFetchRequest,
    principal: Principal = Depends(guard(Action.TOOL_CALL)),
) -> Envelope[dict]:

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

