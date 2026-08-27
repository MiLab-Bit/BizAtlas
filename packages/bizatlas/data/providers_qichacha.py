from __future__ import annotations

import hashlib
from typing import Any

import httpx

from bizatlas.config import get_settings

_QCC_BASE = "https://api.qichacha.com"


def qichacha_configured() -> bool:
    """仅检查 appkey(appkey) 是否存在；真正调用还需 appsecret 做签名。"""
    s = get_settings()
    return bool(s.qichacha_token.strip()) and bool(s.qichacha_secret.strip())


def _sign(params: dict[str, str], appkey: str, appsecret: str) -> str:
    """企查查开放平台签名（appkey+appsecret+排序参数字符串 的 MD5，大写）。

    注：签名顺序以 open.qcc.com 当前文档为准；若服务端返回「签名错误」，
    需核对 appkey/appsecret 与拼接顺序（部分旧版为 appkey+params+appsecret）。
    """
    ordered = "&".join(f"{k}={params[k]}" for k in sorted(params))
    raw = appkey + appsecret + ordered
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def _call(api: str, params: dict[str, str]) -> dict[str, Any]:
    s = get_settings()
    appkey = s.qichacha_token.strip()
    appsecret = s.qichacha_secret.strip()
    if not appkey:
        raise RuntimeError("未配置 qichacha_token（appkey），请在 .env 设置 QICHACHA_TOKEN")
    if not appsecret:
        raise RuntimeError("未配置 qichacha_secret（appsecret），企查查签名必需；请在 .env 设置 QICHACHA_SECRET")
    params = dict(params)
    params["key"] = appkey
    params["token"] = _sign(params, appkey, appsecret)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_QCC_BASE + api, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"企查查网络错误：{exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("企查查返回非 JSON")
    if str(data.get("Status")) != "200" and data.get("Status") not in (200, "200"):
        # 企查查常见：Status=200 成功；非 200 携带 Message
        raise RuntimeError(f"企查查业务错误 Status={data.get('Status')}: {data.get('Message')}")
    return data


def fetch_company_profile(keyword: str) -> dict[str, Any]:
    """经企查查开放平台拉取工商登记 + 失信摘要，返回与 tianyancha 适配器同构的结构。

    流程：ECIEnterpriseInfoSearch（按名搜索拿 KeyNo）→ ECIEnterpriseInfo（工商照面）
    → EciDishonest（失信）。需要 QICHACHA_TOKEN(appkey) + QICHACHA_SECRET(appsecret)。
    """
    name = (keyword or "").strip()
    if not name:
        raise ValueError("企业名为空")

    profile: dict[str, Any] = {
        "source": "qichacha",
        "query": name,
        "basic": None,
        "dishonest": None,
        "candidates": [],
        "ok": False,
        "message": "",
    }

    # 1) 搜索
    try:
        search = _call("/ECIEnterpriseInfoSearch", {"keyword": name, "pageIndex": "1", "pageSize": "5"})
        result = search.get("Result") or {}
        eci_list = result.get("ECIList") or []
        profile["candidates"] = [
            {"name": c.get("Name"), "keyNo": c.get("KeyNo"), "creditCode": c.get("CreditCode")}
            for c in eci_list
            if c.get("Name")
        ]
        pick = next((c for c in eci_list if c.get("Name") == name), None) or (
            eci_list[0] if eci_list else None
        )
        key_no = pick.get("KeyNo") if pick else None
        search_name = pick.get("Name") or name
    except Exception as exc:  # noqa: BLE001
        profile["message"] = f"搜索失败：{exc}"
        return profile

    if not key_no:
        profile["message"] = profile.get("message") or "未查到工商主体"
        return profile

    # 2) 工商照面
    try:
        info = _call("/ECIEnterpriseInfo", {"keyword": key_no})
        r = (info.get("Result") or info) if isinstance(info, dict) else {}
        profile["basic"] = {
            "name": r.get("Name"),
            "creditCode": r.get("CreditCode") or r.get("UniformSocialCreditCode"),
            "legalPerson": r.get("LegalPerson") or r.get("OperManName"),
            "regStatus": r.get("Status") or r.get("RegStatus"),
            "regCapital": r.get("RegistCapi") or r.get("RegCapital"),
            "establishTime": r.get("FoundDate") or r.get("EstablishDate"),
            "companyType": r.get("CompanyType"),
            "regLocation": r.get("Address") or r.get("RegAddr"),
            "industry": r.get("Industry"),
            "businessScope": (r.get("Scope") or "")[:400],
            "socialStaffNum": r.get("EmployeeNum"),
        }
        profile["ok"] = True
        profile["message"] = "ok"
    except Exception as exc:  # noqa: BLE001
        profile["message"] = profile.get("message") or str(exc)
        return profile

    # 3) 失信
    try:
        dish = _call("/EciDishonest", {"keyword": search_name})
        r = dish.get("Result") or {}
        items = r.get("DishonestList") or r.get("Items") or []
        profile["dishonest"] = {
            "count": r.get("Total") if isinstance(r.get("Total"), int) else len(items),
            "items": [
                {
                    "iname": it.get("Iname") or it.get("Name"),
                    "caseCode": it.get("CaseCode") or it.get("CaseNo"),
                    "court": it.get("CourtName") or it.get("Court"),
                }
                for it in (items[:5] if isinstance(items, list) else [])
                if isinstance(it, dict)
            ],
        }
    except Exception as exc:  # noqa: BLE001
        profile["dishonest"] = {"count": None, "items": [], "error": str(exc)}

    return profile
