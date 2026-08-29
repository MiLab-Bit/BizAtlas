from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.contracts.models import AnalyzeRequest, RiskResult
from bizatlas.evaluation import check_release_gate, evidence_coverage
from bizatlas.orchestrator.analyze import run_analyze

GOLDEN = ROOT / "packages" / "bizatlas" / "evaluation" / "golden.json"


def _golden() -> dict:
    if not GOLDEN.exists():
        raise RuntimeError(
            f"golden.json 缺失：请运行生成脚本捕获 3 个 fixture 的精确分数 -> {GOLDEN}"
        )
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_scores_exact():
    """精确回归：任意评分权重/规则改动都会让精确分数漂移，必须 conscious 更新 golden.json。

    这就是 AuditPilot 式 release gate 在分数层面的落地——防止分数悄悄漂移。
    """
    gold = _golden()
    for fid, expect in gold["fixtures"].items():
        res = run_analyze(AnalyzeRequest(company_id=fid))
        assert res["summary"]["grade"] == expect["grade"], f"{fid} grade 漂移"
        assert res["summary"]["score"] == expect["score"], f"{fid} score 漂移"
        dims = {d["id"]: d["score"] for d in res["risk"]["dimensions"]}
        for dim, val in expect["dimensions"].items():
            assert dims.get(dim) == val, f"{fid} 维度 {dim} 漂移"


def test_golden_deterministic():
    """确定性回归：同 fixture 多次研判结果完全一致（不依赖随机/时钟）。"""
    gold = _golden()
    for fid in gold["fixtures"]:
        r1 = run_analyze(AnalyzeRequest(company_id=fid))
        r2 = run_analyze(AnalyzeRequest(company_id=fid))
        assert r1["summary"]["grade"] == r2["summary"]["grade"], f"{fid} grade 不确定"
        assert r1["summary"]["score"] == r2["summary"]["score"], f"{fid} score 不确定"
        assert r1["risk"]["score"] == r2["risk"]["score"], f"{fid} risk.score 不确定"


def test_golden_pipeline_consistency():
    """双路径一致性：pipeline 封装（run_analysis_pipeline）与直接 run_analyze 的评分一致。

    run_analysis_pipeline 以 core=run_analyze(req) 为唯一事实源并原样透传 summary，
    因此其 enriched 结果中的 summary 必须与直接 run_analyze 完全一致。
    """
    gold = _golden()
    for fid in gold["fixtures"]:
        direct = run_analyze(AnalyzeRequest(company_id=fid))
        pipe = run_analysis_pipeline(AnalyzeRequest(company_id=fid))
        assert (
            pipe["summary"]["grade"] == direct["summary"]["grade"]
        ), f"{fid} 双路径 grade 不一致"
        assert (
            pipe["summary"]["score"] == direct["summary"]["score"]
        ), f"{fid} 双路径 score 不一致"


def test_golden_eval_gate():
    """评测基准：3 个 fixture 的发布门禁与证据覆盖率可断言、结构正确。"""
    gold = _golden()
    for fid in gold["fixtures"]:
        res = run_analyze(AnalyzeRequest(company_id=fid))
        rr = RiskResult.model_validate(res["risk"])
        gate = check_release_gate(rr)
        assert "passed" in gate and "evidence_coverage" in gate
        assert 0.0 <= gate["evidence_coverage"] <= 1.0
        cov = evidence_coverage(rr)
        assert 0.0 <= cov <= 1.0
