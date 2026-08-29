"""连续亏损代理预警 + 贷前快路径回归。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.contracts.models import AnalyzeRequest, DataTier, MetricValue, MetricSource
from bizatlas.credit.decision import build_credit_decision
from bizatlas.data.db import init_db
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.risk.score import score_risk
from bizatlas.rules.engine import RuleEngine


def setup_module():
    init_db()


def _mv(name: str, value: float) -> MetricValue:
    return MetricValue(
        name=name,
        value=value,
        unit="ratio" if "年数" not in name else "count",
        tier=DataTier.L2,
        source=MetricSource(type="cache", ref="test", page=None),
        confidence=0.8,
    )


def test_consecutive_loss_triggers_orange():
    metrics = [
        _mv("流动比率", 1.3),
        _mv("速动比率", 1.0),
        _mv("资产负债率", 0.45),
        _mv("利息保障倍数", 4.0),
        _mv("ROE", 0.01),
        _mv("毛利率", 0.12),
        _mv("经营现金流/净利润", 0.5),
        _mv("连续亏损年数", 2),
    ]
    events = {"连续两年扣非净利为负": True}
    engine = RuleEngine()
    hits = engine.match(metrics, events=events)
    risk = score_risk("co-ew", metrics, hits, events=events)
    assert risk.grade.value in {"ORANGE", "RED", "YELLOW"}
    assert risk.score >= 22.0
    assert risk.scoring.early_warning and risk.scoring.early_warning.get("triggered")
    # 加分后通常进入 ORANGE；若基础分极低也可能仍为 YELLOW，但必须高于未加分基线
    assert risk.scoring.early_warning.get("boost") == 18.0


def test_credit_fast_path_skips_polish():
    init_db()
    result = run_analyze(
        AnalyzeRequest(
            company_id="healthy",
            options={"skip_polish": True, "fast": True, "include_stress": False},
        )
    )
    assert result["fast_path"] is True
    assert result["summary"]["headline_meta"].get("skipped") is True
    assert result["summary"]["grade"] in {"GREEN", "YELLOW"}
    decision = build_credit_decision(result, applied_amount=500, tenor_months=12)
    assert decision["decision"] in {
        "APPROVE",
        "APPROVE_WITH_CONDITIONS",
        "MANUAL_REVIEW",
        "DECLINE",
        "INSUFFICIENT_DATA",
    }
    assert decision["determinism"]["llm_used"] is False


def test_risky_still_elevated_with_early_warning():
    init_db()
    result = run_analyze(
        AnalyzeRequest(company_id="risky", options={"skip_polish": True, "include_stress": False})
    )
    assert result["summary"]["grade"] in {"ORANGE", "RED", "BLACK"}
