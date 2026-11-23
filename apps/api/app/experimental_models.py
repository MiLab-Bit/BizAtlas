"""Opt-in, non-decisional experimental risk model endpoint.

All submitted feature/evidence metadata is client-supplied and untrusted.
This endpoint NEVER approves a credit decision or publishes empirical PD.
"""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.auth_deps import get_principal
from bizatlas.contracts.models import AnalyzeRequest, Envelope, RiskResult
from bizatlas.data.temporal_evidence import LicenseStatus, TemporalEvidence
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.risk.feature_bridge import FeatureObservation
from bizatlas.risk.model_service import (
    ExperimentalModelRequest,
    apply_registered_experimental_model,
)

router = APIRouter()


class FeatureInput(BaseModel):
    name: str
    value: float | None
    evidence_id: str
    unit: str


class EvidenceInput(BaseModel):
    evidence_id: str
    source_id: str
    source_sha256: str
    occurred_at: datetime | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    published_at: datetime | None = None
    ingested_at: datetime | None = None
    license_status: LicenseStatus = LicenseStatus.UNVERIFIED


class ExperimentalRiskRequest(BaseModel):
    company_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    observation_at: datetime
    features: list[FeatureInput] = Field(default_factory=list, max_length=128)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=128)


@router.post("/v1/experimental-models/risk")
def experimental_model_risk(
    request: ExperimentalRiskRequest,
    principal=Depends(get_principal),
) -> Envelope[dict]:
    """Return a diagnostic risk model result beside the existing rules score.

    Model directories are configured server-side only. No caller-supplied
    filesystem path, artifact or manifest is accepted.
    """
    manifest_root = os.environ.get("BIZATLAS_MODEL_MANIFEST_DIR")
    artifact_root = os.environ.get("BIZATLAS_MODEL_ARTIFACT_DIR")
    if not manifest_root or not artifact_root:
        raise HTTPException(status_code=503, detail="experimental model registry not configured")
    try:
        analysis = run_analyze(AnalyzeRequest(
            company_id=request.company_id,
            intent="analyze_risk",
            options={"fast": True, "skip_polish": True},
        ))
        risk_payload = analysis.get("risk")
        if not isinstance(risk_payload, dict):
            raise HTTPException(status_code=409, detail="risk result unavailable")
        risk = RiskResult.model_validate(risk_payload)
        enriched = apply_registered_experimental_model(
            risk,
            ExperimentalModelRequest(
                model_id=request.model_id,
                version=request.model_version,
                observation_at=request.observation_at,
                features=tuple(FeatureObservation(**item.model_dump()) for item in request.features),
                evidence=tuple(TemporalEvidence(**item.model_dump()) for item in request.evidence),
            ),
            manifest_directory=Path(manifest_root),
            artifact_directory=Path(artifact_root),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="registered model not found") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Envelope(
        ok=True,
        data={
            "risk": enriched.model_dump(mode="json"),
            "experimental_only": True,
            "evidence_attestation": "CLIENT_SUPPLIED_UNVERIFIED",
            "decision_authority": False,
        },
        meta={"mode": "experimental", "empirical_pd_authorized": False},
    )
