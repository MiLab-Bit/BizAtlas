from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.integrity import sign, verify, tamper_detected
from bizatlas.data.db import init_db
from bizatlas.contracts.models import AnalyzeRequest, RiskResult
from bizatlas.evaluation import check_release_gate
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.workflow.due_diligence import (
    advance_due_diligence,
    review_due_diligence,
    start_due_diligence,
)


# ---------- A. 报告防篡改哈希链 ----------

def test_integrity_sign_and_verify():
    payload = {"company": "x", "score": 42.0, "dimensions": [1, 2, 3], "note": None}
    rec = sign("r1", payload, secret="s3cr3t")
    assert verify(rec, payload, secret="s3cr3t") is True


def test_integrity_tamper_detected():
    payload = {"score": 42.0}
    rec = sign("r1", payload, secret="s3cr3t")
    tampered = dict(payload)
    tampered["score"] = 999.0
    assert verify(rec, tampered, secret="s3cr3t") is False
    assert tamper_detected(rec, tampered, secret="s3cr3t") is True


def test_integrity_wrong_secret_fails():
    payload = {"score": 42.0}
    rec = sign("r1", payload, secret="s3cr3t")
    assert verify(rec, payload, secret="other") is False


# ---------- C. 发布门禁 ----------

def test_release_gate_reproducibility_passes():
    rr = RiskResult.model_validate(run_analyze(AnalyzeRequest(company_id="healthy"))["risk"])
    gate = check_release_gate(rr, require_evidence=False)
    assert gate["passed"] is True


def test_release_gate_evidence_enforced():
    # 用有规则命中但未接入 evidence_refs 的 risky，覆盖率应为 0 → 强制拦截
    rr = RiskResult.model_validate(run_analyze(AnalyzeRequest(company_id="risky"))["risk"])
    gate = check_release_gate(rr, require_evidence=True)
    assert gate["passed"] is False
    assert gate["evidence_coverage"] < 0.95


# ---------- B. 人工复核状态机 ----------

def test_review_gate_blocks_submit_until_approved():
    init_db()
    wf = start_due_diligence(fixture_id="risky")
    advance_due_diligence(wf["id"], action="analyze")
    reported = advance_due_diligence(wf["id"], action="report")
    assert reported["requires_review"] is True

    # 未复核时提交必须被阻断（人在回路硬门禁）
    blocked = False
    try:
        advance_due_diligence(wf["id"], action="submit", confirm=True)
    except ValueError:
        blocked = True
    assert blocked, "高风险结论未复核不应允许提交"

    # 复核通过后可提交
    reviewed = review_due_diligence(
        wf["id"], reviewer="风控总监", decision="approve", comment="同意"
    )
    assert reviewed["review_passed"] is True
    assert reviewed["review"]["status"] == "approved"
    submitted = advance_due_diligence(wf["id"], action="submit", confirm=True)
    assert submitted["stage"] == "submitted"


def test_review_reject_generates_remediation():
    init_db()
    wf = start_due_diligence(fixture_id="risky")
    advance_due_diligence(wf["id"], action="analyze")
    advance_due_diligence(wf["id"], action="report")
    reviewed = review_due_diligence(
        wf["id"], reviewer="合规", decision="reject", comment="不通过"
    )
    assert reviewed["review"]["status"] == "rejected"
    assert len(reviewed["remediation_tasks"]) > 0

    # 驳回后提交仍被阻断
    blocked = False
    try:
        advance_due_diligence(wf["id"], action="submit", confirm=True)
    except ValueError:
        blocked = True
    assert blocked


def test_review_return_rolls_back_to_analyzed():
    init_db()
    wf = start_due_diligence(fixture_id="risky")
    advance_due_diligence(wf["id"], action="analyze")
    advance_due_diligence(wf["id"], action="report")
    reviewed = review_due_diligence(
        wf["id"], reviewer="x", decision="return", comment="重做"
    )
    assert reviewed["stage"] == "analyzed"
    assert reviewed["review_passed"] is False
