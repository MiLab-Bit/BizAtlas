from __future__ import annotations

from typing import Any

import httpx

# 巨潮（巨潮资讯网）免费公告源。无需 key。
# 注意：cninfo 的 Web API 曾多次迁移并加反爬；以下按公开文档规格实现，
# 若运行时返回 404 / 空，多半是端点已迁移或需补 Referer/Cookie，需实网冒烟校准。
_CNINFO_BASE = "https://www.cninfo.com.cn"


def cninfo_configured() -> bool:
    # 免费源，无 key 依赖；始终视为可用（真实可用需实网验证）
    return True


def _resolve_org_id(stock_code: str) -> str:
    """把股票代码解析为 cninfo 的 orgId（组织代码）。

    公开文档端点：/new/information/topSearch?keyWord=<code>
    若端点失效，需改用 /new/data/... 或抓取公司页，或调用方直接传入 orgId。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"{_CNINFO_BASE}/new/disclosure/announcementList",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{_CNINFO_BASE}/new/information/topSearch",
                params={"keyWord": stock_code},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"cninfo orgId 解析网络错误：{exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"cninfo orgId 解析返回非 JSON（端点可能已迁移/反爬）：{exc}") from exc

    # topSearch 返回结构可能有 category 列表，取股票类第一条的 orgId
    def _dig(node: Any) -> str | None:
        if isinstance(node, dict):
            if node.get("orgId"):
                return str(node["orgId"])
            for v in node.values():
                r = _dig(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = _dig(v)
                if r:
                    return r
        return None

    org = _dig(data)
    if not org:
        raise RuntimeError("cninfo 未解析到 orgId，请确认端点或手动传入 orgId")
    return org


def fetch_announcements(stock_code: str, *, org_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """经巨潮拉取上市公司公告列表。

    返回公告 dict 列表：title / time / url / type / announcement_id。
    需先解析 orgId（见 _resolve_org_id），再调用 announcementList。
    """
    code = stock_code.strip()
    if not code:
        raise ValueError("stock_code 为空")
    org = org_id or _resolve_org_id(code)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": f"{_CNINFO_BASE}/new/disclosure/announcementList",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    form = {
        "stockCode": code,
        "orgId": org,
        "pageNum": "1",
        "pageSize": str(limit),
        "announcementTimeStart": "",
        "announcementTimeEnd": "",
        "_": "",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{_CNINFO_BASE}/new/disclosure/announcementList",
                data=form,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"cninfo 公告列表网络错误：{exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"cninfo 公告列表返回非 JSON（端点可能已迁移/反爬）：{exc}") from exc

    announcements = data.get("announcements") or []
    out: list[dict[str, Any]] = []
    for a in announcements[:limit]:
        if not isinstance(a, dict):
            continue
        adj = a.get("adjunctUrl") or ""
        out.append(
            {
                "announcement_id": a.get("announcementId"),
                "title": a.get("announcementTitle"),
                "time": a.get("announcementTime"),
                "type": a.get("adjunctType"),
                "url": f"{_CNINFO_BASE}{adj}" if adj.startswith("/") else adj,
            }
        )
    if not out:
        raise RuntimeError("cninfo 未解析到公告条目（端点可能已迁移/反爬）")
    return out
