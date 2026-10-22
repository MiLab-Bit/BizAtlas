from __future__ import annotations

import time

from bizatlas.contracts.models import Envelope, HealthData
from bizatlas.data.db import init_db
from bizatlas.data.registry import provider_health_list
from bizatlas.ingest.fixtures import list_fixtures
from bizatlas.llm.client import llm_configured
from bizatlas.observability.metrics import default_metrics
from bizatlas.rules.store import load_all_rules
from bizatlas.service.health import liveness, readiness
from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from apps.api.app.main import (
    app,
    settings,
)

router = APIRouter()

@router.get("/v1/healthz")
def healthz() -> dict:
    # liveness 探针：不查 DB/外部依赖，供 k8s/systemd 存活检测（公开，见 _PUBLIC_PATHS）。
    return {"status": "ok", "service": "bizatlas", "version": app.version, "time": time.time()}

@router.get("/v1/health")
def health() -> Envelope[HealthData]:
    db_ok = False
    try:
        init_db()
        db_ok = True
    except Exception:
        db_ok = False

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

@router.get("/v1/fixtures")
def fixtures() -> Envelope[list[str]]:
    return Envelope(ok=True, data=list_fixtures(), meta={"mode": settings.bizatlas_mode})

@router.get("/v1/health/live")
def health_live() -> Envelope[dict]:
    return Envelope(ok=True, data=liveness(), meta={"mode": settings.bizatlas_mode})

@router.get("/v1/health/ready")
def health_ready() -> Envelope[dict]:
    data = readiness()
    return Envelope(ok=data["status"] == "ok", data=data, meta={"mode": settings.bizatlas_mode})

@router.get("/v1/metrics")
def metrics(fmt: str = "prometheus") -> Response:
    """可观测指标：默认 Prometheus 文本格式，?fmt=json 返回结构化快照。"""
    m = default_metrics()
    if fmt == "json":
        from fastapi.responses import JSONResponse

        return JSONResponse(m.snapshot())

    return PlainTextResponse(m.as_prometheus(), media_type="text/plain; version=0.0.4")

