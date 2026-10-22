from __future__ import annotations

import json
import queue
import threading

from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.contracts.models import AnalyzeRequest, Envelope
from bizatlas.data import repo
from bizatlas.ingest.upload import ingest_metrics_file
from bizatlas.observability import observe
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.orchestrator.stream import stream_analysis_pipeline
from bizatlas.orchestrator.trace import build_trace
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from apps.api.app.main import (
    _validate_upload,
    settings,
)
from apps.api.app.temporal_gateway import (
    get_pipeline,
    start_pipeline,
)

router = APIRouter()

@router.post("/v1/analyze")
@observe("api.analyze")
def analyze(req: AnalyzeRequest) -> Envelope[dict]:
    try:
        result = run_analyze(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    degraded = result.get("metrics_count", 0) == 0
    return Envelope(
        ok=True,
        data=result,
        meta={
            "request_id": result.get("task_id"),
            "mode": settings.bizatlas_mode,
            "degraded": degraded,
        },
    )

@router.post("/v1/analyze/pipeline")
@observe("api.analyze_pipeline")
async def analyze_pipeline(req: AnalyzeRequest) -> Envelope[dict]:
    """多 Agent 管线研判：确定性内核 + 分类/规划/研究/写作 Agent。

    返回管线完整产出，并附带可视化执行迹 trace（Agent 卡 / 工具调用 /
    事件时间线 / 证据面板），供前端「调查工作台」回放渲染。

    开启 BIZATLAS_TEMPORAL_ENABLED 时改由 Temporal 工作流执行，但**返回契约不变**
    （仍是完整产出 + trace）；如需异步拿 workflow_id，用 /v1/analyze/pipeline/async。
    """
    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import start_pipeline_and_wait

        try:
            result = await start_pipeline_and_wait(req.model_dump())
        except Exception as exc:  # noqa: BLE001 — 与旧路径保持一致：企业不存在返回 404
            if "not found" in str(exc).lower():
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            raise
        degraded = result.get("metrics_count", 0) == 0
        return Envelope(
            ok=True,
            data=result,
            meta={
                "request_id": result.get("task_id"),
                "mode": settings.bizatlas_mode,
                "pipeline_mode": result.get("pipeline_mode"),
                "degraded": degraded,
                "engine": "temporal",
            },
        )
    try:
        result = run_analysis_pipeline(req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    trace = build_trace(result)
    degraded = result.get("metrics_count", 0) == 0
    return Envelope(
        ok=True,
        data={**result, "trace": trace},
        meta={
            "request_id": result.get("task_id"),
            "mode": settings.bizatlas_mode,
            "pipeline_mode": result.get("pipeline_mode"),
            "degraded": degraded,
        },
    )

@router.post("/v1/analyze/pipeline/async")
async def analyze_pipeline_async(req: AnalyzeRequest) -> Envelope[dict]:
    """异步研判：立即返回 {workflow_id, status}，客户端轮询 /v1/analyze/pipeline/{workflow_id}。

    仅当启用 Temporal 时可用。长任务且客户端可轮询时优先用这个 —— API 不必挂住连接，
    发版/重启也不会中断在途研判。
    """
    if not settings.bizatlas_temporal_enabled:
        raise HTTPException(
            status_code=404, detail="Temporal 编排未启用（BIZATLAS_TEMPORAL_ENABLED=false）"
        )

    out = await start_pipeline(req.model_dump())
    return Envelope(ok=True, data=out, meta={"engine": "temporal"})

@router.get("/v1/analyze/pipeline/{workflow_id}")
async def analyze_pipeline_status(workflow_id: str) -> Envelope[dict]:
    """查询 Temporal 研判工作流进度/结果（进度事件供前端渲染）。

    仅当启用 Temporal 时可用；否则返回 404 指引。
    """
    if not settings.bizatlas_temporal_enabled:
        raise HTTPException(status_code=404, detail="Temporal 编排未启用（BIZATLAS_TEMPORAL_ENABLED=false）")

    try:
        data = await get_pipeline(workflow_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Envelope(ok=True, data=data, meta={"engine": "temporal"})

@router.get("/v1/analyze/pipeline/stream")
async def analyze_pipeline_stream(
    company_id: str,
    task: str = "analyze_risk",
    fast: bool = False,
    workflow_id: str | None = None,
):
    """多 Agent 管线实时流（SSE）：逐步推送 Agent 状态/事件，结束时附完整 trace。

    前端用 EventSource 订阅（GET，便于经 vite 代理同源）。开发态鉴权关闭，无需令牌。
    P1-4：用后台线程驱动管线、队列取事件，空闲 15s 发送 SSE 注释心跳 ": ping"，
    防止 nginx/cloudflared 等长连接因空闲被中间层掐断。

    fast=true：评分内核跳过 LLM 润色，优先出 grade/score（演示控延迟）。

    启用 Temporal 时：若未给 workflow_id 则先启动一个工作流，再轮询其进度事件转发
    （engine=temporal）；否则走原进程内 SSE。
    """

    from bizatlas.contracts.models import AnalyzeRequest

    _sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }

    if settings.bizatlas_temporal_enabled:
        from apps.api.app.temporal_gateway import start_pipeline, stream_pipeline_events

        async def temporal_event_gen():
            wid = workflow_id
            if not wid:
                out = await start_pipeline(
                    {
                        "company_id": company_id,
                        "intent": task,
                        "options": {"skip_polish": fast, "fast": fast, "include_stress": not fast},
                    }
                )
                wid = out["workflow_id"]
            async for ev in stream_pipeline_events(wid):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: {}\n\n"

        return StreamingResponse(temporal_event_gen(), media_type="text/event-stream", headers=_sse_headers)

    req = AnalyzeRequest(
        company_id=company_id,
        intent=task,
        options={"skip_polish": fast, "fast": fast, "include_stress": not fast},
    )

    def event_gen():
        q: "queue.Queue[tuple]" = queue.Queue()

        def _run() -> None:
            try:
                for ev in stream_analysis_pipeline(req):
                    q.put(("data", ev))
            except Exception as exc:  # noqa: BLE001
                q.put(("error", str(exc)))
            finally:
                q.put(("end", None))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        while True:
            try:
                kind, payload = q.get(timeout=15)
            except queue.Empty:
                # 空闲心跳：浏览器 EventSource 自动忽略注释行
                yield ": ping\n\n"
                continue
            if kind == "data":
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps({'message': payload}, ensure_ascii=False)}\n\n"
            else:  # end
                yield "event: end\ndata: {}\n\n"
                break

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.post("/v1/quick/upload-analyze")
async def quick_upload_analyze(
    name: str = Form("上传企业"),
    industry: str = Form(""),
    file: UploadFile = File(...),
    request: Request = None,
) -> Envelope[dict]:
    company = repo.create_company(name, industry)
    content = await _validate_upload(file, request)
    try:
        ingested = ingest_metrics_file(company["id"], file.filename or "metrics.csv", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    analyzed = run_analyze(
        AnalyzeRequest(company_id=company["id"], intent="gen_report", template_id="risk_onepager")
    )
    return Envelope(
        ok=True,
        data={"company": company, "ingest": ingested, "analyze": analyzed},
        meta={"degraded": analyzed.get("metrics_count", 0) == 0},
    )

