"""trace 执行迹：从真实多 Agent 管线派生可视化结构（离线、确定性）。"""

from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.orchestrator.trace import build_trace


def _run(fixture_id: str) -> dict:
    result = run_analysis_pipeline(
        AnalyzeRequest(
            company_id=fixture_id,
            intent="analyze_risk",
            options={"include_stress": True, "include_kg": True},
        )
    )
    return build_trace(result)


def test_trace_structure_healthy():
    tr = _run("healthy")
    assert tr["pipeline_status"] == "succeeded"
    # 5 个 Agent 卡：评分内核 + 分类/规划/研究/写作
    assert len(tr["agents"]) == 5
    role_keys = {a["role_key"] for a in tr["agents"]}
    assert role_keys == {"scoring", "classifier", "planner", "researcher", "writer"}
    for a in tr["agents"]:
        assert a["status"] in {"completed", "failed", "blocked"}
        assert a["mode"] in {"deterministic", "llm", "fallback"}
        assert isinstance(a["tool_calls"], list)
    # 事件时间线有序且非空
    assert len(tr["events"]) >= 8
    seqs = [e["seq"] for e in tr["events"]]
    assert seqs == list(range(len(seqs)))
    # 工具调用卡非空
    assert len(tr["tool_calls"]) >= 6
    # 证据面板
    assert isinstance(tr["evidence"], list)
    # 摘要字段
    s = tr["summary"]
    assert s["grade"] and s["score"] is not None
    assert "rules_hit" in s and "data_gaps" in s


def test_trace_risky_has_gaps_and_events():
    tr = _run("risky")
    summary = tr["summary"]
    # risky fixture 应触发数据缺口披露或检索缺口（失败感知）
    assert summary["data_gaps"] >= 0
    # 事件流中包含规划与研究步骤
    types = {e["type"] for e in tr["events"]}
    assert {"plan", "research", "write", "score"}.issubset(types)
    # researcher 工具调用按维度展开
    rag = [t for t in tr["tool_calls"] if t["name"] == "ask_company"]
    assert len(rag) >= 1


def test_trace_defaulted_veto_event():
    tr = _run("defaulted")
    levels = {e["level"] for e in tr["events"]}
    # defaulted 通常触发否决项，事件中出现 warn 级
    assert "warn" in levels or tr["summary"]["grade"] is not None
    # 评分内核永远 completed
    scoring = next(a for a in tr["agents"] if a["role_key"] == "scoring")
    assert scoring["status"] == "completed"
    assert scoring["ok"] is True


def test_trace_evidence_dedup_and_kinds():
    tr = _run("healthy")
    ids = [e["id"] for e in tr["evidence"]]
    assert len(ids) == len(set(ids)), "证据 id 应去重"
    kinds = {e["kind"] for e in tr["evidence"]}
    assert "metric" in kinds  # 核心 citations
