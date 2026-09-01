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

# 连续亏损代理预警：纯财务加权很难摸到 ORANGE（财务维上限仅 30 分），
# 对「连续 2 年扣非/净利为负」追加固定加分（非地板），并在评分快照中披露口径。
EARLY_WARNING_BOOST = 18.0
EARLY_WARNING_SCORE_FLOOR = 45.0  # 仅用于披露/文档，打分走 BOOST
EARLY_WARNING_RULE_IDS = {"R1011", "R1012"}
EARLY_WARNING_EVENTS = {"连续两年扣非净利为负", "连续亏损"}


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


def _detect_consecutive_loss(
    metrics: list[MetricValue],
    events: dict,
    hits: list[RuleHit],
) -> tuple[bool, str]:
    """检测连续亏损代理条件。返回 (是否命中, 依据说明)。"""
    for flag in EARLY_WARNING_EVENTS:
        if events.get(flag):
            return True, f"事件「{flag}」为真（ST 代理标签，非监管原文）"
    for m in metrics:
        if m.name == "连续亏损年数" and m.value is not None:
            try:
                if float(m.value) >= 2:
                    return True, f"指标「连续亏损年数」={m.value} ≥ 2"
            except (TypeError, ValueError):
                pass
    for h in hits:
        if h.rule_id in EARLY_WARNING_RULE_IDS and h.contribute_to_score:
            return True, f"规则 {h.rule_id}·{h.name} 命中"
    return False, ""


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

    early_warning, early_basis = _detect_consecutive_loss(metrics, events, hits)
    early_warning_applied = False
    if early_warning and not veto_reason:
        # 加分制（非地板）：保留与健康样本的分数重叠，避免 AUC 虚高
        boost = EARLY_WARNING_BOOST
        total = min(100.0, round(total + boost, 2))
        early_warning_applied = True

    grade = _grade(total, veto_reason is not None)
    # 数据不足时不得给出误导性的 GREEN：未知≠安全，标注 UNRATED
    if not veto_reason and completeness < 0.5:
        grade = RiskGrade.UNRATED

    top = sorted(hits, key=lambda h: SEVERITY_SCORE.get(h.severity, 0), reverse=True)
    if veto_reason:
        headline = f"重大风险——{veto_reason}"
    elif early_warning_applied:
        headline = f"建议谨慎——连续亏损代理预警已触发（{early_basis}）"
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

    early_warning_meta: dict | None = None
    if early_warning:
        early_warning_meta = {
            "triggered": True,
            "applied_boost": early_warning_applied,
            "boost": EARLY_WARNING_BOOST,
            "basis": early_basis,
            "disclosure": (
                "连续 2 年扣非/净利为负为 ST 风险警示的公开代理条件，"
                "非监管「被实施 ST 起始年」原文；"
                f"命中后追加 {EARLY_WARNING_BOOST} 分风险分（加分制，非硬地板），可审计。"
            ),
        }

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
            scoring_version="1.1.0",
            weight_snapshot=dict(DIMENSION_WEIGHTS),
            severity_snapshot=dict(SEVERITY_SCORE),
            early_warning=early_warning_meta,
        ),
        computed_at=datetime.now(UTC),
    )
