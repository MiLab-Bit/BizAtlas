"""Temporal 底座相关测试。

分层说明：
- 纯逻辑测试（无需 temporalio）：create_due_diligence 返回形状、状态机纯函数。
- Activity 封装测试：需 temporalio；未安装时整组 skip（temporalio 是可选依赖）。
- 端到端 Workflow 测试：需本地 Temporal server（TEMPORAL_SERVER=1 才跑）。

所有测试离线可采集（不连外网 / 不连 Temporal），保证既有 CI 门禁不被破坏。
"""

from __future__ import annotations

import asyncio
import os

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


# ======================================================================
# Activity 封装（需 temporalio）
# ======================================================================

def test_run_analyze_activity_offline():
    pytest.importorskip("temporalio")
    from bizatlas.temporal.activities import run_analyze_activity

    # skip_polish=True 走确定性快路径，避免离线打 LLM
    result = asyncio.run(
        run_analyze_activity(
            {"company_id": "healthy", "intent": "analyze_risk", "options": {"skip_polish": True, "fast": True}}
        )
    )
    assert isinstance(result, dict)
    assert "risk" in result
    assert result["risk"].get("grade")


# ======================================================================
# 端到端 Workflow（需本地 Temporal server）
# ======================================================================

@pytest.mark.skipif(not os.environ.get("TEMPORAL_SERVER"), reason="需要本地 Temporal server (TEMPORAL_SERVER=1)")
def test_risk_analysis_workflow_integration():
    pytest.importorskip("temporalio")
    import tempfile

    from temporalio.client import Client
    from temporalio.worker import Worker

    from bizatlas.config import get_settings
    from bizatlas.temporal.activities import (
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
            ],
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

    asyncio.run(_run())
