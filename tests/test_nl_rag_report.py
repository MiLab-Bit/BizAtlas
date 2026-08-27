from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from bizatlas.data.db import init_db
from bizatlas.kg.graph import build_guarantee_graph
from bizatlas.orchestrator.analyze import generate_credit_report, generate_onepager_report
from bizatlas.rag.simple import ask_company, index_text
from bizatlas.rules.nl_compiler import compile_rule_from_nl
from bizatlas.rules.store import save_pilot_rule


def test_nl_compiler_threshold():
    rule = compile_rule_from_nl("如果商誉占比超 25% 就预警")
    assert rule["condition"]["metric"] == "商誉占比"
    assert rule["condition"]["op"] == ">"
    assert abs(rule["condition"]["value"] - 0.25) < 1e-9
    assert rule["status"] == "pilot"


def test_nl_save_pilot():
    init_db()
    rule = compile_rule_from_nl("流动比率小于 0.9 高风险")
    saved = save_pilot_rule(rule)
    assert saved["id"]
    assert saved["severity"] == "高"


def test_guarantee_graph_risky():
    g = build_guarantee_graph("risky", fixture_id="risky")
    assert g["nodes"]
    assert g["edges"]


def test_rag_fixture_ask():
    init_db()
    result = ask_company("客户集中度", fixture_id="risky")
    assert result["answer"]
    assert isinstance(result["citations"], list)


def test_rag_index_roundtrip():
    init_db()
    n = index_text("doc-test-rag", "流动比率为 0.85，资产负债率 75%。客户集中度偏高。")
    assert n >= 1
    result = ask_company("流动比率")
    assert "流动" in result["answer"] or result["citations"]


def test_onepager_docx_export():
    init_db()
    out = generate_onepager_report("risky", confirm_export=True)
    assert out["markdown"]
    assert out["docx_path"]
    assert Path(out["docx_path"]).exists()


def test_credit_docx_export():
    init_db()
    out = generate_credit_report("risky", confirm_export=True)
    assert out["credit"]["template_id"] == "credit_assessment"
    assert out["docx_path"]
    assert Path(out["docx_path"]).exists()
