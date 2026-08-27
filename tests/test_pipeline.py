"""多 Agent 编排（阶段 2）测试。

覆盖：
- 离线可运行（无 LLM key 时确定性降级）
- writer-only 保证：pipeline 不改变确定性评分（grade/score/risk 与 run_analyze 一致）
- 失败感知：数据缺口显式披露、RAG 检索缺失显式披露
- 分类 Agent 确定性路由
- 报告生成接入 use_pipeline 后注入 narrative/disclosures
"""

from __future__ import annotations

from bizatlas.agents.classifier import classify_company
from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.agents.planner import plan_research
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.orchestrator.analyze import run_analyze


def test_pipeline_runs_offline():
    """无 LLM 时整套流水线仍可产出（确定性降级），且各 Agent 返回信封。"""
    out = run_analysis_pipeline(AnalyzeRequest(company_id="risky"))
    assert out["pipeline_status"] == "succeeded"
    agents = out["agents"]
    for role in ("classifier", "planner", "researcher", "writer"):
        assert role in agents
        assert agents[role]["ok"] is True
    # 离线默认走确定性
    assert out["pipeline_mode"] in ("deterministic", "fallback")


def test_writer_only_does_not_alter_score():
    """writer-only 铁律：pipeline 的 grade/score/risk 必须与 run_analyze 完全相同。"""
    req = AnalyzeRequest(company_id="risky")
    base = run_analyze(req)
    pipe = run_analysis_pipeline(req)
    assert pipe["summary"]["grade"] == base["summary"]["grade"]
    assert pipe["summary"]["score"] == base["summary"]["score"]
    # writer-only 铁律：确定性评分内容（除计算时间戳外）必须与 run_analyze 一致
    for key in ("company_id", "grade", "score", "dimensions", "hits", "veto", "quality", "evidence_refs", "scoring"):
        assert pipe["risk"][key] == base["risk"][key], key
    # narrative 是叠加层，不应反向污染 risk
    assert "narrative" in pipe


def test_failure_awareness_data_gaps():
    """规划 Agent 应能显式枚举缺失的核心指标（失败感知）。"""
    # 构造仅含 2 个指标、无行业、含估算来源的"贫数据"场景
    risk = {
        "grade": "YELLOW",
        "score": 35.0,
        "quality": {"completeness": 0.25, "conflicts": 0, "tier_mix": {"L1": 0, "L2": 1, "L3": 1}},
        "hits": [],
        "dimensions": [
            {"id": "财务", "score": 40.0, "weight": 0.30},
        ],
        "veto": {"triggered": False, "reason": None},
    }
    meta = {"name": "贫数据公司", "industry": "", "metrics": [{"name": "流动比率"}]}
    classification = {"category": "other", "routing_hints": ["财务", "经营"]}
    res = plan_research(risk, meta, classification)
    gaps = res.output["data_gaps"]
    codes = {g["code"] for g in gaps}
    assert "missing_metrics" in codes
    assert "low_completeness" in codes
    assert "estimate_tier" in codes
    # 弱证据维度也应被标出（财务维度得分>0 但无命中证据）
    assert "weak_evidence" in codes


def test_researcher_discloses_empty_rag():
    """检索 Agent：本地无资料时显式披露缺口，绝不返回伪证据。"""
    # risky fixture 不会索引'股权质押异常'这类特定查询 → 应触发 retrieval_gap
    out = run_analysis_pipeline(AnalyzeRequest(company_id="risky"))
    researcher = out["agents"]["researcher"]
    # 至少存在未命中项（fixture 资料有限），且都被显式披露
    assert "gap_disclosures" in researcher["output"]
    # 未命中查询数 == 缺口披露数（一一对应，无遗漏）
    unresolved = researcher["output"]["unresolved"]
    gaps = researcher["output"]["gap_disclosures"]
    assert len(unresolved) == len(gaps)


def test_classifier_deterministic_routing():
    """分类 Agent：行业关键词确定性归类。"""
    mfg = classify_company({"name": "XX 智能制造有限公司", "industry": "高端装备制造"})
    assert mfg.output["category"] == "manufacturing"
    assert "财务" in mfg.output["routing_hints"]

    tech = classify_company({"name": "XX 科技", "industry": "人工智能软件"})
    assert tech.output["category"] == "tech"

    unknown = classify_company({"name": "XX 集团", "industry": ""})
    assert unknown.output["category"] == "other"
    assert any("通用口径" in n for n in unknown.notes)


def test_report_injects_pipeline_output():
    """use_pipeline 开启时，onepager 报告应注入 narrative 与 disclosures。"""
    from bizatlas.orchestrator.analyze import generate_onepager_report

    rep = generate_onepager_report("risky", use_pipeline=True)
    payload = rep["onepager"]
    assert "narrative" in payload
    assert "disclosures" in payload
    assert payload["narrative"].get("executive_summary")
    # 默认（不开 pipeline）不应含 narrative 键
    rep_default = generate_onepager_report("risky", use_pipeline=False)
    assert "narrative" not in rep_default["onepager"]
