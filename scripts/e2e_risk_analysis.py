"""Run the REAL BizAtlas RiskAnalysisWorkflow on the local Temporal dev server."""
import asyncio
import time

from temporalio.client import Client

from bizatlas.temporal.common import RiskAnalysisInput
from bizatlas.temporal.workflows.risk_analysis import RiskAnalysisWorkflow

TQ = "bizatlas-task-queue"


async def main() -> None:
    c = await Client.connect("localhost:7233")
    inp = RiskAnalysisInput(
        company_id="risky",
        intent="analyze_risk",
        options={"fast": True, "skip_polish": True},
    )
    t0 = time.time()
    res = await c.execute_workflow(
        RiskAnalysisWorkflow.run, inp, id=f"ra-real-{int(t0)}", task_queue=TQ
    )
    print(f"WORKFLOW OK in {time.time()-t0:.1f}s", flush=True)
    if isinstance(res, dict):
        print("keys:", sorted(res.keys())[:30], flush=True)
        for k in ("company_id", "grade", "score", "risk_level", "pipeline_mode", "metrics_count"):
            if k in res:
                print(f"  {k} = {res[k]}", flush=True)
        tr = res.get("trace")
        if isinstance(tr, dict):
            print("  trace keys:", sorted(tr.keys())[:15], flush=True)


if __name__ == "__main__":
    asyncio.run(main())
