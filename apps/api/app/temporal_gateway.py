"""FastAPI → Temporal 网关（异步）。

职责：把 HTTP 请求翻译成 Temporal 的 start_workflow / query / execute_update，
并把结果回传给路由层做 Envelope 封装。

关键约束：
- temporalio 为可选依赖，本模块内所有 temporalio 引用均**懒导入**，确保
  `from apps.api.app.main import app` 在离线/未装 temporalio 时不报错（既有 pytest 不受影响）。
- 仅当 config.BIZATLAS_TEMPORAL_ENABLED=True 时，main 中的路由才会调用本模块；
  关闭时路由走原有同步路径，行为完全不变。
- 这里只做"编排调用"，不写业务逻辑；业务规则都在 Workflow/Activity 里。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from bizatlas.config import get_settings


async def _client() -> Any:
    from bizatlas.temporal.client import get_client

    return await get_client()


def _temporal_on() -> bool:
    return bool(get_settings().bizatlas_temporal_enabled)


# ======================================================================
# 多 Agent 研判管线
# ======================================================================

async def start_pipeline(req_dict: dict[str, Any]) -> dict[str, Any]:
    from bizatlas.temporal.common import RiskAnalysisInput
    from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

    settings = get_settings()
    client = await _client()
    # 只取已知字段（AnalyzeRequest 还含 message/document_ids，RiskAnalysisInput 不接受）
    inp = RiskAnalysisInput(
        company_id=req_dict["company_id"],
        intent=req_dict.get("intent", "analyze_risk"),
        template_id=req_dict.get("template_id"),
        options=req_dict.get("options") or {},
    )
    wid = inp.workflow_id or f"ra-{inp.company_id}-{int(time.time() * 1000)}"
    handle = await client.start_workflow(
        RiskAnalysisWorkflow.run, inp, id=wid, task_queue=settings.temporal_task_queue
    )
    return {"workflow_id": handle.id, "status": "running"}


async def start_pipeline_and_wait(req_dict: dict[str, Any]) -> dict[str, Any]:
    """同步语义：启动工作流并等待其最终结果。

    用途：给「需要一次性拿完整产出」的调用方（前端调查工作台非实时模式）保留原有
    API 契约 —— 返回体与 `run_analysis_pipeline` 同构（含 trace），但执行仍然跑在
    Temporal 上（可重试、可观测、崩溃可续跑）。
    """
    from bizatlas.temporal.common import RiskAnalysisInput
    from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

    settings = get_settings()
    client = await _client()
    inp = RiskAnalysisInput(
        company_id=req_dict["company_id"],
        intent=req_dict.get("intent", "analyze_risk"),
        template_id=req_dict.get("template_id"),
        options=req_dict.get("options") or {},
    )
    wid = inp.workflow_id or f"ra-{inp.company_id}-{int(time.time() * 1000)}"
    handle = await client.start_workflow(
        RiskAnalysisWorkflow.run, inp, id=wid, task_queue=settings.temporal_task_queue
    )
    return await handle.result()


async def get_pipeline(workflow_id: str) -> dict[str, Any]:
    from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

    client = await _client()
    handle = client.get_workflow_handle(workflow_id)
    status = await handle.query(RiskAnalysisWorkflow.get_status)
    progress = await handle.query(RiskAnalysisWorkflow.get_progress)
    result = await handle.query(RiskAnalysisWorkflow.get_result) if status == "completed" else None
    return {"workflow_id": workflow_id, "status": status, "progress": progress, "result": result}


async def stream_pipeline_events(workflow_id: str) -> AsyncIterator[dict[str, Any]]:
    """轮询管线进度，逐条 yield 新增事件，最后补一条 done（携带完整 trace）。

    与旧进程内 SSE 的收尾事件对齐：前端 InvestigationPage 依赖
    `{"type": "done", "trace": ...}` 回放渲染，缺了它页面会停在中间态。
    """
    from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

    client = await _client()
    handle = client.get_workflow_handle(workflow_id)
    cursor = 0
    while True:
        status = await handle.query(RiskAnalysisWorkflow.get_status)
        progress = await handle.query(RiskAnalysisWorkflow.get_progress)
        for ev in progress[cursor:]:
            yield ev
        cursor = len(progress)
        if status == "completed":
            break
        if status == "failed":
            yield {"type": "error", "message": "风险研判工作流执行失败"}
            return
        await asyncio.sleep(0.5)
    try:
        result = await handle.query(RiskAnalysisWorkflow.get_result) or {}
    except Exception:  # noqa: BLE001 — 结果不可用时仍要正常收尾
        result = {}
    yield {"type": "done", "trace": result.get("trace") or {}}


# ======================================================================
# 贷前尽调
# ======================================================================

async def _query_with_retry(handle: Any, query_method: Any, attempts: int = 6) -> Any:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return await handle.query(query_method)
        except Exception as exc:  # noqa: BLE001 — 启动竞态：workflow 尚未跑首个 task
            last = exc
            await asyncio.sleep(0.3)
    raise last if last else RuntimeError("query failed")


async def start_due_diligence_wf(req_dict: dict[str, Any]) -> dict[str, Any]:
    from bizatlas.temporal.common import DueDiligenceInput
    from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow

    settings = get_settings()
    client = await _client()
    inp = DueDiligenceInput(**req_dict)
    wid = f"dd-{inp.fixture_id or inp.company_id or 'x'}-{int(time.time() * 1000)}"
    handle = await client.start_workflow(
        DueDiligenceWorkflow.run, inp, id=wid, task_queue=settings.temporal_task_queue
    )
    return await _query_with_retry(handle, DueDiligenceWorkflow.get_snapshot)


async def get_due_diligence_wf(workflow_id: str) -> dict[str, Any]:
    from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow

    client = await _client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        return await handle.query(DueDiligenceWorkflow.get_snapshot)
    except Exception:  # noqa: BLE001 — 已结束（submit 后 workflow 关闭）→ 回退 SQLite 镜像
        from bizatlas.data import repo
        from bizatlas.workflow.due_diligence import _snapshot

        if repo.get_workflow(workflow_id):
            return _snapshot(workflow_id)
        raise


async def advance_due_diligence_wf(
    workflow_id: str, action: str, confirm: bool, manual_flags: dict[str, bool] | None
) -> dict[str, Any]:
    from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow

    client = await _client()
    handle = client.get_workflow_handle(workflow_id)
    try:
        return await handle.execute_update(
            DueDiligenceWorkflow.advance, args=[action, confirm, manual_flags]
        )
    except Exception:
        # submit 是终态：Workflow 完成可能先于 Update 回值（AcceptedUpdateCompletedWorkflow），
        # 此时改取 Workflow 的最终结果快照。
        if action == "submit":
            try:
                return await handle.result()
            except Exception:
                raise
        raise


async def review_due_diligence_wf(
    workflow_id: str, decision: str, comment: str, reviewer: str
) -> dict[str, Any]:
    from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow

    client = await _client()
    handle = client.get_workflow_handle(workflow_id)
    return await handle.execute_update(
        DueDiligenceWorkflow.review, args=[decision, comment, reviewer]
    )
