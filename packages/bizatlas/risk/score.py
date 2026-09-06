from __future__ import annotations

import math

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
from bizatlas.risk.behavioral import compute_behavioral
from bizatlas.risk.calibration import calibrate, master_scale_from_pd
from bizatlas.risk.distress import compute_distress
from bizatlas.risk.reason_codes import build_reason_codes

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

# v2 综合分融合权重（规则严重度 / 财务困境 PD / 商业行为）
# 任一层缺失时按可用层重分配（见 enrich_risk）。
BLEND_WEIGHTS = {
    "rule": 0.50,
    "distress": 0.30,
    "behavioral": 0.20,
}


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


# ---------------------------------------------------------------------------
# B-RCF v2.0.1 融合层：量纲统一 + 审慎叠加
#
# 规则分是 0-100「严重度」，困境层输出的是「违约概率 PD」，二者量纲不同。
# 直接 PD×100 与规则分加权会让低 PD 层把高危主体稀释（实测 risky 96.2 → 54.1
# ORANGE），因此这里先把 PD 统一到严重度尺度，再按银行 overlay 惯例融合：
# 以规则分为基准，其他层仅在「显著劣于规则分」时向上叠加（只升不降），
# 数据缺口不参与叠加——绝不把「未知」当「安全」。
# ---------------------------------------------------------------------------
_PD_SEV_LOW = 0.001  # PD ≈ 0.1% → 严重度 0（投资级下沿）
_PD_SEV_HIGH = 0.99  # PD = 99% → 严重度 100
UPLIFT_MIN_DELTA = 10.0  # 层严重度至少高出规则分 10 分才计入叠加（过滤噪声）
BEHAVIORAL_MIN_COMPLETENESS = 0.5  # 行为层已知维度不足一半时不参与叠加


def severity_from_pd(pd: float | None) -> float | None:
    """违约概率 → 0-100 严重度分（对数几率尺度线性映射，与主标尺同序）。

    PD 与风险严重度不是线性关系：PD 从 1% 升到 2% 的风险增幅远大于 50% 升到 51%。
    因此在对数几率（log-odds）尺度上做线性映射，与评分卡 PDO 口径一致：
    PD 0.1% → 0.0，1% → 20.1，5% → 34.5，13% → 43.5，50% → 60.0，95% → 85.7。
    """
    if pd is None:
        return None
    p = min(max(float(pd), 1e-6), 1 - 1e-6)
    lo = math.log(_PD_SEV_LOW / (1 - _PD_SEV_LOW))
    hi = math.log(_PD_SEV_HIGH / (1 - _PD_SEV_HIGH))
    cur = math.log(p / (1 - p))
    return round(max(0.0, min(100.0, (cur - lo) / (hi - lo) * 100.0)), 2)


def blend_severity(rule_score: float, layers: dict[str, float | None]) -> tuple[float, dict]:
    """以规则分为基准，按「显著劣化才上调」叠加各层严重度（只升不降）。

    Args:
        rule_score: 规则引擎严重度分（0-100，越高越危险）。
        layers: {层名: 严重度分 | None}，None 表示该层数据缺口，不参与叠加。

    Returns:
        (综合分, 审计信息{uplift_total, uplift_by_layer})
    """
    uplift = 0.0
    used: dict[str, float] = {}
    for name, sev in layers.items():
        if sev is None:
            continue
        delta = sev - rule_score
        if delta >= UPLIFT_MIN_DELTA:
            w = BLEND_WEIGHTS[name]
            uplift += w * delta
            used[name] = round(w * delta, 2)
    combined = round(min(100.0, max(0.0, rule_score + uplift)), 2)
    return combined, {"uplift_total": round(uplift, 2), "uplift_by_layer": used}


def enrich_risk(
    risk: RiskResult,
    metrics: list[MetricValue],
    events: dict | None = None,
    hits: list[RuleHit] | None = None,
    *,
    distress: dict | None = None,
    behavioral: dict | None = None,
) -> RiskResult:
    """B-RCF v2.0.1 融合层：规则严重度 + 财务困境 + 商业行为 → 综合风险。

    不破坏现有 credit/decision.py（仍读 GREEN..BLACK 五档 grade）。本函数负责产出
    10 级银行主标尺 master_scale、综合 PD、以及 FICO 式 reason codes。

    融合口径（v2.0.1）:
    - 统一量纲：困境层 PD 先经 severity_from_pd 映射到 0-100 严重度（对数几率尺度），
      不再直接 PD×100 与规则分加权，避免量纲不等价稀释高危主体。
    - 审慎叠加：以规则分为基准，其他层仅当「显著劣于规则分（≥ UPLIFT_MIN_DELTA）」
      时向上叠加，只升不降；数据缺口（PD 缺失 / 行为层已知维度不足一半）不参与
      叠加，绝不把「未知」当「安全」。
    - PD/主标尺经 calibration 层（logistic + 文档化先验）产出。
    """
    events = events or {}

    distress = distress if distress is not None else compute_distress(metrics)
    behavioral = behavioral if behavioral is not None else compute_behavioral(events)

    rule_score = float(risk.score)

    # 困境层：PD 缺失即数据缺口，该层不参与叠加（不再按 0 计入）
    distress_sev = severity_from_pd(distress.get("pd"))
    # 行为层：已知维度过少时不参与叠加，避免用个别维度代表整体商业行为
    beh_sev = (
        float(behavioral.get("composite") or 0.0)
        if behavioral.get("available")
        and float(behavioral.get("completeness") or 0.0) >= BEHAVIORAL_MIN_COMPLETENESS
        else None
    )

    combined, blend_audit = blend_severity(
        rule_score, {"distress": distress_sev, "behavioral": beh_sev}
    )

    veto = risk.veto.triggered
    if veto:
        new_grade = RiskGrade.BLACK
    else:
        new_grade = _grade(combined, False)
        if risk.quality.completeness < 0.5:
            new_grade = RiskGrade.UNRATED

    risk.score = combined
    risk.grade = new_grade

    # PD + 10 级主标尺（calibration 层）
    cal = calibrate(risk.model_dump(mode="json"))
    risk.pd = cal.pd
    risk.master_scale = cal.master_scale

    # FICO 式 reason codes
    reasons = build_reason_codes(risk.dimensions, distress, behavioral, hits=hits, top_n=8)

    risk.modules = {
        "version": "2.0.1",
        "fusion_mode": "rule_baseline_uplift",
        "blend_weights": {
            "rule": 1.0,
            "distress": BLEND_WEIGHTS["distress"] if distress_sev is not None else 0.0,
            "behavioral": BLEND_WEIGHTS["behavioral"] if beh_sev is not None else 0.0,
        },
        "layer_severity": {
            "rule": rule_score,
            "distress": distress_sev,
            "behavioral": beh_sev,
        },
        **blend_audit,
        "distress": distress,
        "behavioral": behavioral,
        "reason_codes": reasons,
        "calibration": {
            "pd": cal.pd,
            "lgd": cal.lgd,
            "expected_loss": cal.expected_loss,
            "master_scale": cal.master_scale,
            "rationale": cal.rationale,
        },
    }
    risk.scoring.scoring_version = "2.0.1"
    return risk
