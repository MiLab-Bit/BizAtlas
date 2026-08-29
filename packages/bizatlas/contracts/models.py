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
    UNRATED = "UNRATED"


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


class Evidence(BaseModel):
    """稳定证据对象：每条事实 / 指标 / 风险结论都可回溯到此处。

    对标 AuditPilot 的 evidence_refs 设计——结论不再只靠文件名字符串，
    而是挂稳定 evidence_id + 文档哈希 + 页码/坐标，支撑可审计的证据链。
    """

    evidence_id: str  # 稳定 UUID，关联 MetricValue/RuleHit/RiskResult.evidence_refs
    source_type: str  # document | standard | kg | heuristic | api
    doc_id: str | None = None
    page: int | None = None
    bbox: str | None = None  # 版面坐标 "x,y,w,h"，缺省为空
    doc_sha256: str | None = None  # 来源文档 SHA256，防篡改与溯源
    content_snippet: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetricValue(BaseModel):
    name: str
    value: float | None = None
    unit: str = ""
    tier: DataTier = DataTier.L1
    as_of: date | None = None
    source: MetricSource | None = None
    evidence_refs: list[str] = Field(default_factory=list)  # 关联 Evidence.evidence_id
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
    evidence_refs: list[str] = Field(default_factory=list)  # 关联 Evidence.evidence_id


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


class ScoringSnapshot(BaseModel):
    """评分口径快照：固化当次计算的公式版本与权重，保证历史分数可复现。

    对标 AuditPilot 对'规则版本 / 权重 / 阈值'的固化要求——
    没有它，'当时的评分口径'无法还原，分数漂移也无从追查。
    """

    scoring_version: str = "1.0.0"
    weight_snapshot: dict[str, float] = Field(default_factory=dict)
    severity_snapshot: dict[str, float] = Field(default_factory=dict)
    # 连续亏损等代理预警的抬分政策（可空）；写入快照便于审计复现
    early_warning: dict[str, Any] | None = None


class RiskResult(BaseModel):
    company_id: str
    grade: RiskGrade
    ratable: bool = True
    score: float
    headline: str
    dimensions: list[DimensionScore] = Field(default_factory=list)
    hits: list[RuleHit] = Field(default_factory=list)
    veto: VetoInfo = Field(default_factory=VetoInfo)
    quality: QualityInfo = Field(default_factory=QualityInfo)
    evidence_refs: list[str] = Field(default_factory=list)  # 本次结论关联的全部证据
    scoring: ScoringSnapshot = Field(default_factory=ScoringSnapshot)
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
