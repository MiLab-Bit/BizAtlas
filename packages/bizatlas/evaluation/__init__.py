"""评测与发布门禁（对标 AuditPilot 的分层评测 + release gate）。

- ``evidence_coverage`` / ``check_release_gate``：把"证据覆盖、评分可复现"做成
  发布前可断言的硬指标，防止分数悄悄漂移或结论不可溯源。
- 黄金值回归由 tests/test_golden_regression.py 负责（固化 3 个 fixture 的精确分数）。
"""

from __future__ import annotations

from typing import Any

from bizatlas.contracts.models import RiskResult


def evidence_coverage(risk_result: RiskResult) -> float:
    """命中规则中被证据覆盖的比例。

    每条 RuleHit 至少挂一个 evidence_refs 才算可溯源。无命中时视为满分（无需溯源）。
    """
    hits = risk_result.hits
    if not hits:
        return 1.0
    covered = sum(1 for h in hits if h.evidence_refs)
    return round(covered / len(hits), 4)


def check_release_gate(
    risk_result: RiskResult,
    *,
    min_evidence_coverage: float = 0.95,
    require_evidence: bool = False,
) -> dict[str, Any]:
    """发布前门禁：返回 {passed, evidence_coverage, reasons}。

    - 评分可复现：权重/阈值快照必须存在（否则历史分数口径丢失）。
    - 证据覆盖率：达到阈值才允许发布；``require_evidence=False`` 时仅告警不阻断
      （证据链全面接入后应改为 True，形成硬门禁）。
    """
    reasons: list[str] = []
    passed = True

    snap = risk_result.scoring
    if not snap.weight_snapshot or not snap.severity_snapshot:
        passed = False
        reasons.append("评分权重/阈值快照缺失，历史分数不可复现")

    cov = evidence_coverage(risk_result)
    if require_evidence and cov < min_evidence_coverage:
        passed = False
        reasons.append(f"证据覆盖率 {cov} < {min_evidence_coverage}，结论不可溯源")
    elif cov < min_evidence_coverage:
        reasons.append(
            f"证据覆盖率 {cov}（当前未强制，证据链接入后将成为硬门禁）"
        )

    return {
        "passed": passed,
        "evidence_coverage": cov,
        "reasons": reasons,
    }
