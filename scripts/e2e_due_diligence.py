"""Run the REAL BizAtlas DueDiligenceWorkflow (Update/Query state machine) on Temporal."""
import asyncio
import time

from temporalio.client import Client

from bizatlas.temporal.common import DueDiligenceInput
from bizatlas.temporal.workflows.due_diligence import DueDiligenceWorkflow

TQ = "bizatlas-task-queue"


async def main() -> None:
    c = await Client.connect("localhost:7233")
    h = await c.start_workflow(
        DueDiligenceWorkflow.run,
        DueDiligenceInput(fixture_id="risky"),
        id=f"dd-real-{int(time.time())}",
        task_queue=TQ,
    )
    snap = await h.query(DueDiligenceWorkflow.get_snapshot)
    print(f"start      stage={snap.get('stage')} ready={snap.get('required_ready')} blockers={snap.get('blockers')}", flush=True)
    print(f"           workflow_id={h.id}", flush=True)

    try:
        snap = await h.execute_update(DueDiligenceWorkflow.advance, args=["analyze"])
    except Exception as e:  # noqa: BLE001
        print(f"analyze    FAILED: {type(e).__name__}: {e}", flush=True)
        snap = await h.query(DueDiligenceWorkflow.get_snapshot)
        print(f"           snapshot checklist={[(i['id'], i['done']) for i in (snap.get('checklist') or [])]}", flush=True)
        return
    grade = ((snap.get("analyze") or {}).get("summary") or {}).get("grade")
    print(f"analyze    stage={snap.get('stage')} grade={grade} metrics={((snap.get('analyze') or {}).get('metrics_count'))}", flush=True)

    snap = await h.execute_update(DueDiligenceWorkflow.advance, args=["report"])
    print(f"report     stage={snap.get('stage')} requires_review={snap.get('requires_review')} report_id={(snap.get('report') or {}).get('report_id')}", flush=True)

    if snap.get("requires_review") and not snap.get("review_passed"):
        snap = await h.execute_update(
            DueDiligenceWorkflow.review,
            args=["approve", "本地端到端验证：人工复核通过", "local-e2e"],
        )
        print(f"review     stage={snap.get('stage')} review_passed={snap.get('review_passed')}", flush=True)

    try:
        snap = await h.execute_update(DueDiligenceWorkflow.advance, args=["submit", True])
        print(f"submit     stage={snap.get('stage')} export_path={(snap.get('report') or {}).get('export_path')}", flush=True)
        print("history:", snap.get("history"), flush=True)
    except Exception as e:  # noqa: BLE001
        # submit 会让 Workflow 完成，完成可能先于 Update 回值（AcceptedUpdateCompletedWorkflow）
        print(f"submit     update 提前结束（{type(e).__name__}），改取 workflow 最终结果…", flush=True)
        final = await h.result()
        print(f"submit     最终 stage={final.get('stage')} export_path={(final.get('report') or {}).get('export_path')}", flush=True)
        print("history:", final.get("history"), flush=True)
    print("WORKFLOW_ID:", h.id, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
