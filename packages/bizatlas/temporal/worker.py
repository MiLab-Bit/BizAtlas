"""Temporal Worker 启动器。

注册 Workflow 与 Activity，连接 Temporal 集群并开始轮询任务队列。
独立进程运行（与 FastAPI 分离），由 scripts/run_worker.py 或 `bizatlas-worker` 入口拉起。

依赖：temporalio（可选依赖，见 pyproject [project.optional-dependencies].temporal）。
运行前需有一个可达的 Temporal 集群：本地用 `temporal server start-dev`，或 docker-compose.temporal.yml。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import logging

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from bizatlas.config import get_settings
from bizatlas.temporal.activities import (
    build_trace_activity,
    classify_activity,
    compute_checklist_activity,
    export_onepager_activity,
    generate_report_activity,
    load_template_activity,
    mirror_dd_activity,
    plan_activity,
    research_activity,
    run_analyze_activity,
    start_dd_activity,
    write_activity,
)
from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow
from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

log = logging.getLogger("bizatlas.temporal.worker")

# 同步 Activity 的并行度。本层的 Activity 内部是阻塞调用（LLM HTTP / SQLite / 报告导出），
# 走线程池而非事件循环，因此这里的上限即"同时在跑的 Activity 数"。
_ACTIVITY_WORKERS = 20

# 领域模块（bizatlas.*）在导入期会做路径解析 / 读取模板等非确定性副作用，
# 这些只在编排层调用，因此对沙箱设为直通（passthrough），避免沙箱校验工作流
# 时误报 RestrictedWorkflowAccessError（例如 pathlib.Path.resolve）。
_SANDBOX_RUNNER = SandboxedWorkflowRunner(
    restrictions=dataclasses.replace(
        SandboxRestrictions.default,
        passthrough_modules=SandboxRestrictions.default.passthrough_modules | {"bizatlas"},
    )
)


def run() -> None:
    """控制台脚本入口：阻塞运行 Worker。"""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    # 确保系统记录库（SQLite）schema 就绪：Worker 是独立进程，不会经过 FastAPI 启动钩子，
    # 而尽调 Workflow 的 Activity 会读写 companies/workflows 等表。
    from bizatlas.data.db import init_db

    init_db()
    client = await Client.connect(
        settings.temporal_address, namespace=settings.temporal_namespace
    )
    log.info(
        "starting Temporal worker | task_queue=%s namespace=%s address=%s",
        settings.temporal_task_queue,
        settings.temporal_namespace,
        settings.temporal_address,
    )
    # 同步 Activity 必须提供 activity_executor：temporalio 会把它们提交到线程池执行，
    # 从而不阻塞 Worker 的 asyncio 事件循环（见 activities.py 顶部说明）。
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ACTIVITY_WORKERS) as activity_executor:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[RiskAnalysisWorkflow, DueDiligenceWorkflow],
            workflow_runner=_SANDBOX_RUNNER,
            activities=[
                run_analyze_activity,
                classify_activity,
                plan_activity,
                research_activity,
                write_activity,
                build_trace_activity,
                start_dd_activity,
                compute_checklist_activity,
                export_onepager_activity,
                generate_report_activity,
                mirror_dd_activity,
                load_template_activity,
            ],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    run()
