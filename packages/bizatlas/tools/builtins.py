"""内置受治理工具：把商舆的「重/外部」能力登记进默认注册表。

原则（对齐内核确定性 + 失败感知）：
- 本地 RAG 检索：始终离线可用，低风险，不进沙箱（避免子进程开销拖慢研判）。
- 外部数据源拉取：网络依赖强、可能挂起/失败，必须沙箱隔离 + 熔断。
- 视觉解析：可能触发外部 VLM 后端，必须沙箱隔离 + 熔断。

底层函数均懒加载（调用时才 import），保证注册表本身在无 akshare 等
可选依赖时也能安全初始化——这是离线/断网环境可部署的前提。
"""

from __future__ import annotations

from typing import Any

from bizatlas.tools.permissions import Scope
from bizatlas.tools.registry import ToolSpec, default_registry


def _rag_search(query: str, *, company_id: str | None = None, fixture_id: str | None = None) -> dict[str, Any]:
    from bizatlas.rag.simple import ask_company

    return ask_company(query, company_id=company_id, fixture_id=fixture_id)


def _provider_fetch(
    symbol: str,
    *,
    provider: str = "akshare",
    company_id: str | None = None,
    company_name: str | None = None,
) -> list[dict[str, Any]]:
    if provider == "akshare":
        from bizatlas.data.providers_akshare import fetch_stock_basic_metrics

        return fetch_stock_basic_metrics(symbol)
    if provider == "tushare":
        from bizatlas.data.providers_tushare import fetch_stock_basic_metrics

        return fetch_stock_basic_metrics(symbol)
    raise ValueError(f"unsupported provider: {provider}")


def _vision_parse(pdf_path: str, source_ref: str) -> dict[str, Any]:
    from bizatlas.ingest.vision import run_vision_pipeline

    return run_vision_pipeline(pdf_path, source_ref).model_dump()


def register_default_tools(registry: Any | None = None) -> None:
    """把内置工具登记进注册表（应用启动时调用一次）。幂等。"""
    reg = registry or default_registry()
    if reg.has("rag.search"):
        return
    reg.register(
        ToolSpec(
            name="rag.search",
            scope=Scope.DATA_READ,
            fn=_rag_search,
            timeout=10.0,
            use_sandbox=False,
            description="本地资料检索（RAG，离线可用）",
        )
    )
    reg.register(
        ToolSpec(
            name="data.provider_fetch",
            scope=Scope.TOOL_CALL,
            fn=_provider_fetch,
            timeout=20.0,
            use_sandbox=True,
            description="外部行情/工商数据拉取（沙箱隔离+熔断）",
        )
    )
    reg.register(
        ToolSpec(
            name="ingest.vision_parse",
            scope=Scope.DATA_READ,
            fn=_vision_parse,
            timeout=30.0,
            use_sandbox=True,
            description="复杂版面/印章视觉解析（沙箱隔离+熔断）",
        )
    )
