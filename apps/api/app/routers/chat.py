from __future__ import annotations

from typing import Any

from bizatlas.auth.rbac import Principal
from bizatlas.contracts.models import Envelope
from bizatlas.identity import model_providers as mp_store
from bizatlas.llm.agent import handle_agent_message
from bizatlas.llm.background import background_reply, start_background_session
from bizatlas.llm.client import set_llm_scope, set_request_provider
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from apps.api.app.main import (
    BackgroundChatRequest,
    BackgroundStartRequest,
    ChatRequest,
    _sse,
)
from apps.api.auth_deps import get_principal

router = APIRouter()

@router.post("/v1/chat")
def chat(req: ChatRequest, principal: Principal = Depends(get_principal)) -> Envelope[dict]:

    # 注入用户自带 provider（若有 active 配置），否则回退平台设置。
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    set_request_provider(
        {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    )
    set_llm_scope(principal.user_id)
    try:
        result = handle_agent_message(
            req.message.strip(),
            company_id=req.company_id,
            fixture_id=req.fixture_id,
            context=req.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        set_request_provider(None)
    return Envelope(ok=True, data=result)

@router.post("/v1/chat/stream")
def chat_stream(req: ChatRequest, principal: Principal = Depends(get_principal)) -> StreamingResponse:
    """流式版 /v1/chat（SSE）。

    - ask_doc/unknown 意图：逐 token 流式输出 RAG 回答（后端 /v1/chat 保持非流式不变）。
    - 其它意图：在路由线程内同步算出完整结果，整段以单个 SSE 事件发出（保持兼容）。
    流式路径显式透传用户 active provider，不依赖跨线程 ContextVar。
    """
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    provider_dict = {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    set_request_provider(provider_dict)
    set_llm_scope(principal.user_id)
    message = req.message.strip()
    try:
        from bizatlas.llm.intent import classify_intent

        intent = classify_intent(message).get("intent")
        if intent in (None, "ask_doc", "unknown"):
            from bizatlas.rag.simple import stream_ask_company

            def _gen() -> Any:
                try:
                    for ev in stream_ask_company(
                        message,
                        company_id=req.company_id,
                        fixture_id=req.fixture_id,
                        provider=provider_dict,
                    ):
                        yield _sse(ev)
                finally:
                    set_request_provider(None)

            return StreamingResponse(_gen(), media_type="text/event-stream")

        # 非流式意图：在路由线程内同步计算（ContextVar 对本线程有效），整段发出
        from bizatlas.llm.agent import handle_agent_message

        result = handle_agent_message(
            message,
            company_id=req.company_id,
            fixture_id=req.fixture_id,
            context=req.context,
        )

        def _gen() -> Any:
            try:
                yield _sse({"type": "result", "data": result})
            finally:
                set_request_provider(None)

        return StreamingResponse(_gen(), media_type="text/event-stream")
    except Exception as exc:  # noqa: BLE001
        set_request_provider(None)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/v1/background/start")
def background_start(req: BackgroundStartRequest) -> Envelope[dict]:

    try:
        data = start_background_session(req.company_name, industry=req.industry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Envelope(ok=True, data=data)

@router.post("/v1/background/chat")
def background_chat(req: BackgroundChatRequest, principal: Principal = Depends(get_principal)) -> Envelope[dict]:

    # 注入用户自带 provider（若有 active 配置），否则回退平台设置。
    provider = (
        mp_store.get_active_provider(principal.user_id, "text")
        if principal.user_id != "anonymous"
        else None
    )
    set_request_provider(
        {k: provider[k] for k in ("api_key", "base_url", "model")} if provider else None
    )
    set_llm_scope(principal.user_id)
    try:
        data = background_reply(
            req.message,
            company_id=req.company_id,
            company_name=req.company_name,
            fixture_id=req.fixture_id,
            history=req.history,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        set_request_provider(None)
    return Envelope(ok=True, data=data)

