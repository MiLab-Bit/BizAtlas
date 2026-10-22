from __future__ import annotations

from bizatlas.contracts.models import Envelope
from bizatlas.data import repo
from bizatlas.ingest.upload import ingest_metrics_file
from bizatlas.kg.graph import build_guarantee_graph
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from apps.api.app.main import (
    CreateCompanyRequest,
    _validate_upload,
)

router = APIRouter()

@router.get("/v1/companies")
def companies() -> Envelope[list[dict]]:
    return Envelope(ok=True, data=repo.list_companies())

@router.post("/v1/companies")
def create_company(req: CreateCompanyRequest) -> Envelope[dict]:
    created = repo.create_company(req.name, req.industry)
    return Envelope(ok=True, data=created)

@router.get("/v1/companies/{company_id}")
def get_company(company_id: str) -> Envelope[dict]:
    company = repo.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="company not found")
    metrics = repo.load_metrics(company_id)
    return Envelope(
        ok=True,
        data={**company, "metrics_count": len(metrics), "metrics": [m.model_dump(mode="json") for m in metrics]},
    )

@router.post("/v1/companies/{company_id}/documents")
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

@router.get("/v1/companies/{company_id}/graph")
def company_graph(company_id: str, fixture_id: str | None = None) -> Envelope[dict]:
    fid = fixture_id
    if company_id in {"healthy", "risky", "defaulted"}:
        fid = company_id
    data = build_guarantee_graph(company_id, fixture_id=fid)
    return Envelope(ok=True, data=data)

