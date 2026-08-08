from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest
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
