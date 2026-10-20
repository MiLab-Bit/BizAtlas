"""Temporal Worker 启动器（统一到 openclaw_core.temporal.run_worker）。

注册 Workflow 与 Activity，连接 Temporal 集群并开始轮询任务队列。
独立进程运行（与 FastAPI 分离），由 scripts/run_worker.py 或 `bizatlas-worker` 入口拉起。
"""
from __future__ import annotations

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
from openclaw_core.temporal import run_worker


def run() -> None:
    """控制台脚本入口：阻塞运行 Worker。"""
    settings = get_settings()
    # Worker 是独立进程，不会经过 FastAPI 启动钩子；尽调 Workflow 的 Activity 会读写
    # companies/workflows 等表，故在此确保系统记录库（SQLite）schema 就绪。
    from bizatlas.data.db import init_db

    run_worker(
        [RiskAnalysisWorkflow, DueDiligenceWorkflow],
        [
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
        task_queue=settings.temporal_task_queue,
        namespace=settings.temporal_namespace,
        address=settings.temporal_address,
        activity_workers=20,
        passthrough_modules={"bizatlas"},
        on_connect=init_db,
    )


if __name__ == "__main__":
    run()
