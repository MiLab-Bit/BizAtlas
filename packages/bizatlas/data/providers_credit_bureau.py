"""征信数据源（P0-③ 真实数据源占位 + 优雅降级）。

接口契约：声明「征信报告查询」标准返回，未配置凭据时**显式降级**
（返回 ok=False + 原因，**绝不抛异常、绝不编造数字**）。

接入具体征信机构（百行/朴道/央行征信前置系统等）时，在
:func:`_fetch_real` 内填充实调用即可，上层无需改动。
"""
from __future__ import annotations

from typing import Any

from bizatlas.config import get_settings


def credit_bureau_configured() -> bool:
    """是否配置了征信凭据（credit_bureau_token）。"""
    return bool(getattr(get_settings(), "credit_bureau_token", "").strip())


def fetch_credit_report(keyword: str) -> dict[str, Any]:
    """拉取企业征信摘要。

    Returns:
        {source, query, ok, message, data}
        - ok=False 且 data=None：降级/未配置，上层应跳过而非报错。
    """
    profile: dict[str, Any] = {
        "source": "credit_bureau",
        "query": (keyword or "").strip(),
        "ok": False,
        "message": "",
        "data": None,
    }
    if not profile["query"]:
        profile["message"] = "企业名为空"
        return profile
    if not credit_bureau_configured():
        profile["message"] = "未配置 credit_bureau_token（征信数据源未启用），降级跳过"
        return profile
    # TODO: 接入具体征信机构 API（保留 _fetch_real 钩子）
    profile["message"] = "征信 provider 已配置但实调用未实现（待接入具体机构）"
    return profile


def _fetch_real(keyword: str) -> dict[str, Any]:
    """实调用钩子：接入具体征信机构时实现。

    预期返回结构化征信摘要（逾期、查询次数、担保余额等），需带来源时间戳。
    """
    raise NotImplementedError("征信实调用待接入具体机构 API")
