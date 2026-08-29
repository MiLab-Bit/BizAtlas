"""SSE 流式管线生成器离线测试（不启动 HTTP，直接测生成器协议）。"""

from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.orchestrator.stream import stream_analysis_pipeline


def test_stream_sequence_and_trace():
    req = AnalyzeRequest(company_id="healthy")
    events = list(stream_analysis_pipeline(req))

    types = [e["type"] for e in events]
    assert types[0] == "task_created"
    assert types.count("agent_start") == 5
    assert types.count("agent_done") == 5
    assert types[-1] == "done"

    # 每对 agent_start/agent_done 角色对齐
    roles_seen = [e["role"] for e in events if e["type"] in ("agent_start", "agent_done")]
    assert roles_seen == [
        "scoring", "scoring",
        "classifier", "classifier",
        "planner", "planner",
        "researcher", "researcher",
        "writer", "writer",
    ]

    # agent_done 含完整字段
    for e in events:
        if e["type"] == "agent_done":
            assert "ok" in e and "mode" in e and "summary" in e

    done = events[-1]
    assert done["pipeline_status"] == "succeeded"
    trace = done["trace"]
    assert trace["pipeline_status"] == "succeeded"
    assert len(trace["agents"]) == 5
    assert len(trace["events"]) > 0
    assert trace["summary"]["grade"] is not None


def test_stream_risky_fixture():
    req = AnalyzeRequest(company_id="risky")
    events = list(stream_analysis_pipeline(req))
    assert events[-1]["type"] == "done"
    assert events[-1]["trace"]["summary"]["grade"] is not None
