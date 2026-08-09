from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import httpx

# 巨潮资讯网（cninfo）免费公告源，无需 key。
#
# 正确端点（与 akshare 同源）：POST /new/hisAnnouncement/query
# 旧代码用的 /new/disclosure/announcementList 与 /new/information/topSearch
# 均已返回 404，属于历史迁移后的失效端点，此处按实测可用规格重写。
#
# stock 参数不是 JSON 列表，而是逗号分隔的「代码,orgId」字符串；
# orgId 来自各市场的静态股票列表 JSON（沪深京统一用 szse_stock.json）。
_BASE = "https://www.cninfo.com.cn"
_DETAIL = f"{_BASE}/new/disclosure/detail"

# 市场 -> (股票列表 JSON 地址, column 参数)
_MARKETS: dict[str, tuple[str, str]] = {
    "沪深京": (f"{_BASE}/new/data/szse_stock.json", "szse"),
    "港股": (f"{_BASE}/new/data/hke_stock.json", "hke"),
    "三板": (f"{_BASE}/new/data/gfzr_stock.json", "third"),
}

_CST = timezone(timedelta(hours=8))
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"{_BASE}/new/disclosure/announcementList",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def cninfo_configured() -> bool:
    # 免费源，无 key 依赖；始终视为可用（真实可用需实网验证）
    return True


@lru_cache(maxsize=8)
def _get_code_org_map(market: str) -> dict[str, str]:
    """拉取某市场的「股票代码 -> orgId」映射并缓存。

    沪深京统一用 szse_stock.json（实测该文件覆盖沪市/深市/创业板全量）。
    """
    if market not in _MARKETS:
        raise ValueError(f"不支持的 cninfo 市场：{market}（可选：{list(_MARKETS)}）")
    url, _ = _MARKETS[market]
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"cninfo 股票列表获取失败：{exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"cninfo 股票列表返回非 JSON：{exc}") from exc

    try:
        stock_list = data["stockList"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"cninfo 股票列表结构异常：{exc}") from exc

    return {
        str(it["code"]): str(it["orgId"])
        for it in stock_list
        if it.get("code") and it.get("orgId")
    }


def _fmt_ts(ms: Any) -> str | None:
    """cninfo 公告时间为毫秒时间戳，转成 YYYY-MM-DD（北京时间）。"""
    try:
        ts = int(ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts / 1000, tz=_CST).strftime("%Y-%m-%d")


def fetch_announcements(
    stock_code: str,
    *,
    market: str = "沪深京",
    org_id: str | None = None,
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """经巨潮拉取上市公司公告列表。

    返回公告 dict 列表：announcement_id / title / time / type / sec_code /
    sec_name / url（详情页链接）。

    stock_code 需为市场内有效代码；orgId 优先使用入参 org_id，否则从市场
    股票列表自动解析。start_date/end_date 为 YYYY-MM-DD，留空则取最新公告。
    """
    code = (stock_code or "").strip()
    if not code:
        raise ValueError("stock_code 为空")
    if market not in _MARKETS:
        raise ValueError(f"不支持的 cninfo 市场：{market}")

    _, column = _MARKETS[market]
    org = org_id or _get_code_org_map(market).get(code)
    if not org:
        raise RuntimeError(f"cninfo 未找到股票代码 {code} 的 orgId（市场={market}）")

    se_date = f"{start_date}~{end_date}" if (start_date and end_date) else ""

    form = {
        "pageNum": "1",
        "pageSize": str(limit),
        "column": column,
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{code},{org}",  # 关键：逗号分隔的「代码,orgId」，非 JSON
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": se_date,
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.post(
                f"{_BASE}/new/hisAnnouncement/query",
                data=form,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            j = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"cninfo 公告列表网络错误：{exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"cninfo 公告列表返回非 JSON：{exc}") from exc

    announcements = j.get("announcements") or []
    out: list[dict[str, Any]] = []
    for a in announcements[:limit]:
        if not isinstance(a, dict):
            continue
        aid = a.get("announcementId")
        ts = _fmt_ts(a.get("announcementTime"))
        out.append(
            {
                "announcement_id": aid,
                "title": a.get("announcementTitle"),
                "time": ts,
                "type": a.get("adjunctType"),
                "sec_code": a.get("secCode"),
                "sec_name": a.get("secName"),
                "url": (
                    f"{_DETAIL}?stockCode={code}"
                    f"&announcementId={aid}&orgId={org}&announcementTime={ts}"
                    if aid
                    else ""
                ),
            }
        )
    if not out:
        raise RuntimeError(
            f"cninfo 未解析到 {code} 的公告条目（可能代码/市场不匹配或无公告）"
        )
    return out
