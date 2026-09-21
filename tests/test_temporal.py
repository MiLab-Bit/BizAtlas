"""Temporal 底座相关测试。

分层说明：
- 纯逻辑测试（无需 temporalio）：create_due_diligence 返回形状、状态机纯函数、
  跨边界数据类型 —— 这些在 CI（未装 temporalio）里也会真实执行。
- Activity 封装测试：需 temporalio；未安装时整组 skip（temporalio 是可选依赖）。
- 端到端 Workflow 测试：需本地 Temporal server（TEMPORAL_SERVER=1 才跑）。

所有测试离线可采集（不连外网 / 不连 Temporal），保证既有 CI 门禁不被破坏。

⚠️ 约定：Activity 一律是**同步** `def`（见 activities.py 顶部说明），测试直接调用即可，
不要用 `asyncio.run(...)` 包一层。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict

import pytest


# ======================================================================
# 纯逻辑（不依赖 temporalio）
# ======================================================================

def test_create_due_diligence_shape():
    """重构后的 create_due_diligence 应返回未快照的原始结构，供 Temporal Activity 使用。"""
    from bizatlas.workflow.due_diligence import create_due_diligence

    raw = create_due_diligence(fixture_id="healthy")
    assert {"workflow_id", "template_id", "company_id", "stage", "payload"}.issubset(raw)
    assert raw["template_id"] == "due_diligence"
    assert raw["stage"] in ("checklist", "ready")
    assert isinstance(raw["payload"], dict)


def test_due_diligence_pure_helpers():
    """_required_ready / _build_remediation_tasks 为纯函数，状态逻辑可在 Workflow 内安全使用。"""
    from bizatlas.workflow.due_diligence import _build_remediation_tasks, _required_ready

    checklist = [
        {"id": "c1", "required": True, "done": True},
        {"id": "c2", "required": False, "done": False},
    ]
    assert _required_ready(checklist) is True
    checklist[0]["done"] = False
    assert _required_ready(checklist) is False

    tasks = _build_remediation_tasks({"hits": [{"name": "流动比率过低", "severity": "高", "dimension": "财务"}]})
    assert tasks and tasks[0]["priority"] == "P0"


def test_create_due_diligence_branches():
    """覆盖 create_due_diligence 的非 fixture 分支：新建企业 / 缺失企业报错。"""
    from bizatlas.workflow.due_diligence import create_due_diligence

    # 无 company_id、无 fixture → 按 name 新建企业
    raw = create_due_diligence(name="尽调新企业")
    assert raw["company_id"]
    assert raw["stage"] in ("checklist", "ready")
    assert raw["payload"]["history"][0]["action"] == "start"

    # company_id 不存在 → 明确报错（不让 Workflow 静默继续）
    with pytest.raises(ValueError):
        create_due_diligence(company_id="co-does-not-exist-xyz")


def test_cross_boundary_dataclasses_are_plain():
    """跨 Temporal 边界的数据必须是纯 dataclass（默认 JSON DataConverter 可序列化）。

    本模块只依赖标准库，因此**在未安装 temporalio 的 CI 里也会执行**。
    """
    from bizatlas.temporal.common import (
        AnalysisProgressEvent,
        DueDiligenceInput,
        RiskAnalysisInput,
    )

    ri = RiskAnalysisInput(company_id="healthy", options={"fast": True})
    d = asdict(ri)
    assert d["company_id"] == "healthy"
    assert d["intent"] == "analyze_risk"  # 默认值
    assert d["options"] == {"fast": True}
    assert d["workflow_id"] is None

    dd = DueDiligenceInput(fixture_id="risky")
    assert asdict(dd)["fixture_id"] == "risky"
    assert asdict(dd)["industry"] == ""

    ev = AnalysisProgressEvent(type="agent_done", role="classifier", ok=True, summary="赛道 X")
    dumped = ev.to_dict()
    assert dumped["type"] == "agent_done"
    assert dumped["role"] == "classifier"
    assert dumped["ok"] is True
    # None 字段应被裁掉，避免 SSE 帧里出现无意义空值
    assert "trace" not in dumped
    assert "label" not in dumped


def test_due_diligence_input_accepts_both_keys():
    """尽调入参支持 fixture_id 或 company_id 两种来源（网关与 Workflow 共用）。"""
    from bizatlas.temporal.common import DueDiligenceInput

    assert DueDiligenceInput(company_id="co-1").company_id == "co-1"
    assert DueDiligenceInput(fixture_id="risky").fixture_id == "risky"
    assert DueDiligenceInput().company_id is None and DueDiligenceInput().fixture_id is None


# ======================================================================
# Activity 封装（需 temporalio；注意 Activity 是同步函数）
# ======================================================================

def test_run_analyze_activity_offline():
    pytest.importorskip("temporalio")
    from bizatlas.temporal.activities import build_trace_activity, run_analyze_activity

    # skip_polish=True 走确定性快路径，避免离线打 LLM。
    # Activity 是同步 def，直接调用（不要再包 asyncio.run）。
    result = run_analyze_activity(
        {"company_id": "healthy", "intent": "analyze_risk", "options": {"skip_polish": True, "fast": True}}
    )
    assert isinstance(result, dict)
    assert "risk" in result
    assert result["risk"].get("grade")

    # 执行迹由独立 Activity 生成（CPU 密集，已从 Workflow 中下沉）
    trace = build_trace_activity(result)
    assert isinstance(trace, dict)
    assert "summary" in trace


def test_activities_are_synchronous():
    """防止回归：Activity 写成 async def 会阻塞 Worker 事件循环（见 activities.py 顶部说明）。"""
    temporalio = pytest.importorskip("temporalio")  # noqa: F841
    import inspect

    from bizatlas.temporal import activities as acts

    names = [n for n in acts.__all__ if n.endswith("_activity")]
    assert names, "activities.__all__ 应导出 activity 函数"
    offenders = [n for n in names if inspect.iscoroutinefunction(getattr(acts, n))]
    assert not offenders, f"以下 Activity 不应是 async def：{offenders}"


# ======================================================================
# 端到端 Workflow（需本地 Temporal server）
# ======================================================================

@pytest.mark.skipif(not os.environ.get("TEMPORAL_SERVER"), reason="需要本地 Temporal server (TEMPORAL_SERVER=1)")
def test_risk_analysis_workflow_integration():
    pytest.importorskip("temporalio")
    import concurrent.futures

    from temporalio.client import Client
    from temporalio.worker import Worker

    from bizatlas.config import get_settings
    from bizatlas.temporal.activities import (
        build_trace_activity,
        classify_activity,
        plan_activity,
        research_activity,
        run_analyze_activity,
        write_activity,
    )
    from bizatlas.temporal.common import RiskAnalysisInput
    from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

    settings = get_settings()

    async def _run():
        client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
        # 同步 Activity 必须提供 activity_executor（否则 Worker 构造即报
        # "Activity ... is not async so an activity_executor must be present"）
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            async with Worker(
                client,
                task_queue=settings.temporal_task_queue,
                workflows=[RiskAnalysisWorkflow],
                activities=[
                    run_analyze_activity,
                    classify_activity,
                    plan_activity,
                    research_activity,
                    write_activity,
                    build_trace_activity,
                ],
                activity_executor=executor,
            ):
                handle = await client.start_workflow(
                    RiskAnalysisWorkflow.run,
                    RiskAnalysisInput(company_id="healthy", options={"skip_polish": True, "fast": True}),
                    id=f"test-ra-{os.getpid()}",
                    task_queue=settings.temporal_task_queue,
                )
                result = await handle.result()
                assert result["pipeline_status"] == "succeeded"
                assert result["pipeline_mode"]
                assert "trace" in result

    asyncio.run(_run())
