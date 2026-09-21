"""Temporal Client 工厂（懒连接 + 模块级缓存）。

仅在使用时连接，且缓存到模块级变量，避免 FastAPI 每个请求重连。
注意：temporalio 是可选依赖，本模块在被调用时才 import，确保离线/未装 temporalio
时 import 不会失败（tests 与 legacy 路径不受影响）。
"""

from __future__ import annotations

from typing import Any

_client: Any | None = None


async def get_client() -> Any:
    """返回（并缓存）一个 Temporal Client 实例。"""
    global _client
    if _client is not None:
        return _client
    from temporalio.client import Client

    from bizatlas.config import get_settings

    settings = get_settings()
    _client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    return _client


def reset_client() -> None:
    """测试/重载配置时清空缓存。"""
    global _client
    _client = None
