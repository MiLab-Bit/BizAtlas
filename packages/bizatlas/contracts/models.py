from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class RiskGrade(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"
    BLACK = "BLACK"


class DataTier(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    failed_partial = "failed_partial"
    awaiting_human = "awaiting_human"


class Envelope(BaseModel, Generic[T]):
    ok: bool = True
    data: T | None = None
    error: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MetricSource(BaseModel):
    type: str  # document | api | cache | estimate
    ref: str
    page: int | None = None


class MetricValue(BaseModel):
    name: str
    value: float | None = None
    unit: str = ""
    tier: DataTier = DataTier.L1
    as_of: date | None = None
    source: MetricSource | None = None
    confidence: float = 1.0


class RuleHit(BaseModel):
    rule_id: str
    name: str
    dimension: str
    severity: str
    message: str
    metrics: list[MetricValue] = Field(default_factory=list)
    contribute_to_score: bool = True
    explain: str = ""


class DimensionScore(BaseModel):
    id: str
    score: float
    weight: float


class VetoInfo(BaseModel):
    triggered: bool = False
    reason: str | None = None


class QualityInfo(BaseModel):
    completeness: float = 1.0
    conflicts: int = 0
    tier_mix: dict[str, float] = Field(default_factory=dict)


class RiskResult(BaseModel):
    company_id: str
    grade: RiskGrade
    score: float
    headline: str
    dimensions: list[DimensionScore] = Field(default_factory=list)
    hits: list[RuleHit] = Field(default_factory=list)
    veto: VetoInfo = Field(default_factory=VetoInfo)
    quality: QualityInfo = Field(default_factory=QualityInfo)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalyzeRequest(BaseModel):
    company_id: str
    intent: str = "analyze_risk"
    message: str | None = None
    document_ids: list[str] | None = None
    template_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    id: str
    name: str
    enabled: bool
    status: str
    ok: bool
    message: str = ""


class HealthData(BaseModel):
    service: str = "bizatlas-api"
    version: str = "0.1.0"
    mode: str
    providers: list[ProviderHealth] = Field(default_factory=list)
    db_ok: bool = False
    rules_loaded: int = 0
    llm_configured: bool = False
    llm_model: str = ""
