from __future__ import annotations

from datetime import UTC, datetime

from bizatlas.contracts.models import (
    DimensionScore,
    MetricValue,
    QualityInfo,
    RiskGrade,
    RiskResult,
    RuleHit,
    ScoringSnapshot,
    VetoInfo,
)

DIMENSION_WEIGHTS = {
    "财务": 0.30,
    "经营": 0.25,
    "行业": 0.15,
    "舆情": 0.15,
    "关联": 0.15,
}

SEVERITY_SCORE = {"高": 25.0, "中": 12.0, "低": 5.0}


def _grade(score: float, veto: bool) -> RiskGrade:
    if veto:
        return RiskGrade.BLACK
    if score < 20:
        return RiskGrade.GREEN
    if score < 40:
        return RiskGrade.YELLOW
    if score < 60:
        return RiskGrade.ORANGE
    if score < 80:
        return RiskGrade.RED
    return RiskGrade.BLACK


def score_risk(
    company_id: str,
    metrics: list[MetricValue],
    hits: list[RuleHit],
    events: dict | None = None,
    *,
    conflicts: int = 0,
) -> RiskResult:
    events = events or {}
    veto_reason = None
    if events.get("失信被执行") or events.get("dishonest_executor"):
        veto_reason = "命中失信被执行人"
    elif events.get("破产重整") or events.get("bankruptcy"):
        veto_reason = "破产重整迹象"

    dim_raw: dict[str, float] = {k: 0.0 for k in DIMENSION_WEIGHTS}
    for hit in hits:
        if not hit.contribute_to_score:
            continue
        dim = hit.dimension if hit.dimension in dim_raw else "财务"
        dim_raw[dim] += SEVERITY_SCORE.get(hit.severity, 10.0)

    dimensions: list[DimensionScore] = []
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        # cap each dimension contribution base at 100 before weight
        dim_score = min(100.0, dim_raw[dim] * 2.0)
        dimensions.append(DimensionScore(id=dim, score=round(dim_score, 2), weight=weight))
        total += dim_score * weight

    total = min(100.0, round(total, 2))
    completeness = round(min(1.0, len(metrics) / 8), 2)
    grade = _grade(total, veto_reason is not None)
    # 数据不足时不得给出误导性的 GREEN：未知≠安全，标注 UNRATED
    if not veto_reason and completeness < 0.5:
        grade = RiskGrade.UNRATED

    top = sorted(hits, key=lambda h: SEVERITY_SCORE.get(h.severity, 0), reverse=True)
    if veto_reason:
        headline = f"重大风险——{veto_reason}"
    elif top:
        headline = f"{'建议谨慎' if total >= 40 else '整体可控'}——{top[0].message}"
    elif metrics:
        headline = "暂无明显规则命中，建议结合行业与经营定性复核"
    else:
        headline = "数据不足，风险结论降级，请补充财报或启用数据源"

    tier_counts = {"L1": 0, "L2": 0, "L3": 0}
    for m in metrics:
        tier_counts[m.tier.value] = tier_counts.get(m.tier.value, 0) + 1
    total_m = max(1, len(metrics))
    tier_mix = {k: round(v / total_m, 2) for k, v in tier_counts.items()}

    # 归集本次结论关联的全部证据 id（用于证据覆盖率校验 / 发布门禁）
    evidence_refs: list[str] = []
    for h in hits:
        evidence_refs.extend(h.evidence_refs or [])
    for m in metrics:
        evidence_refs.extend(getattr(m, "evidence_refs", []) or [])
    # 去重保序
    seen: set[str] = set()
    evidence_refs = [e for e in evidence_refs if not (e in seen or seen.add(e))]

    return RiskResult(
        company_id=company_id,
        grade=grade,
        score=total,
        headline=headline,
        dimensions=dimensions,
        hits=hits,
        veto=VetoInfo(triggered=veto_reason is not None, reason=veto_reason),
        quality=QualityInfo(
            completeness=completeness,
            conflicts=conflicts,
            tier_mix=tier_mix,
        ),
        evidence_refs=evidence_refs,
        ratable=(grade != RiskGrade.UNRATED),
        scoring=ScoringSnapshot(
            scoring_version="1.0.0",
            weight_snapshot=dict(DIMENSION_WEIGHTS),
            severity_snapshot=dict(SEVERITY_SCORE),
        ),
        computed_at=datetime.now(UTC),
    )
