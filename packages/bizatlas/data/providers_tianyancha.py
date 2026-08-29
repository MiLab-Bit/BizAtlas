from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

import httpx

from bizatlas.config import get_settings

CORE_CALL = "https://mcp.tianyancha.com/v1/core/tools/call"


def tianyancha_configured() -> bool:
    return bool(get_settings().tianyancha_token.strip())


def _auth_header() -> str:
    token = get_settings().tianyancha_token.strip()
    if token.lower().startswith("bearer "):
        return token
    return token


def _call_tool_http(tool_name: str, arguments: dict[str, Any]) -> Any:
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"tool_name": tool_name, "arguments": arguments, "format": "json"}
    with httpx.Client(timeout=45.0) as client:
        resp = client.post(CORE_CALL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data.get("error_description") or data.get("error"))
    content = data.get("content") if isinstance(data, dict) else data
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw": content}
    return content


def _resolve_tyc() -> str | None:
    found = shutil.which("tyc")
    if found:
        return found
    # repo-local toolchain
    root = get_settings().root
    for rel in (
        ".tools/node-v22.18.0-win-x64/tyc.cmd",
        ".tools/node-v22.18.0-win-x64/tyc",
        ".tools/node-v22.18.0-win-x64/node_modules/tyc-cli/dist/index.js",
    ):
        path = root / rel
        if path.exists():
            return str(path)
    return None


def _call_tool_cli(group: str, method: str, search_key: str) -> Any:
    """Prefer tyc-cli when available — more stable TLS on Windows than raw httpx."""
    tyc = _resolve_tyc()
    if not tyc:
        raise RuntimeError("tyc-cli 未安装")
    if tyc.endswith(".js"):
        node = shutil.which("node") or str(get_settings().root / ".tools/node-v22.18.0-win-x64/node.exe")
        base_cmd = [node, tyc]
    else:
        base_cmd = [tyc]
    # ensure auth matches .env token
    token = get_settings().tianyancha_token.strip()
    if token:
        subprocess.run(
            [*base_cmd, "init", "--authorization", token, "--no-verify"],
            check=False,
            capture_output=True,
            timeout=30,
        )
    proc = subprocess.run(
        [*base_cmd, group, method, search_key, "--compact", "--full"],
        check=False,
        capture_output=True,
        timeout=60,
    )
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError((stderr or stdout or "tyc 调用失败")[:400])
    out = stdout.strip()
    if not out:
        raise RuntimeError("tyc 无输出")
    # stdout may include banner noise; take first JSON object/array
    start_obj = out.find("{")
    start_arr = out.find("[")
    starts = [i for i in (start_obj, start_arr) if i >= 0]
    if not starts:
        raise RuntimeError(f"tyc 输出非 JSON：{out[:200]}")
    start = min(starts)
    return json.loads(out[start:])


def _call_tool(tool_name: str, arguments: dict[str, Any], *, cli: tuple[str, str] | None = None) -> Any:
    # CLI first for Windows TLS stability
    if cli:
        try:
            key = str(arguments.get("searchKey") or arguments.get("keyword") or "")
            return _call_tool_cli(cli[0], cli[1], key)
        except Exception:
            pass
    return _call_tool_http(tool_name, arguments)


def search_companies(keyword: str, *, limit: int = 5) -> list[dict[str, Any]]:
    data = _call_tool(
        "search_companies",
        {"searchKey": keyword, "pageNum": 1, "pageSize": limit},
        cli=("company", "companies"),
    )
    items: list[Any] = []
    if isinstance(data, dict):
        items = data.get("items") or data.get("result") or []
        if not items and isinstance(data.get("sources"), dict):
            for v in data["sources"].values():
                if isinstance(v, dict) and isinstance(v.get("items"), list):
                    items = v["items"]
                    break
    elif isinstance(data, list):
        items = data
    if not isinstance(items, list):
        return []
    return [row for row in items[:limit] if isinstance(row, dict)]


# ---- 近似匹配：把「腾讯控股」之类含公司结构的名称归一成品牌核心 ----
_BRAND_SUFFIXES = [
    "控股集团有限公司", "控股股份有限公司", "集团股份有限公司",
    "控股有限公司", "集团有限公司", "股份有限公司", "有限责任公司",
    "控股集团", "控股", "集团", "股份", "有限公司", "公司",
]


def _normalize_brand(name: str) -> str:
    """去掉尾部公司结构后缀，得到品牌核心（腾讯控股 -> 腾讯）。"""
    s = (name or "").strip()
    if not s:
        return s
    changed = True
    while changed and len(s) > 1:
        changed = False
        for suf in _BRAND_SUFFIXES:
            if s.endswith(suf):
                s = s[: -len(suf)]
                changed = True
                break
    return s


def _safe_search(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        return search_companies(keyword, limit=limit)
    except Exception:  # noqa: BLE001
        return []


def _extract_base(reg: Any) -> dict[str, Any] | None:
    if not isinstance(reg, dict):
        return None
    sources = reg.get("sources") if isinstance(reg.get("sources"), dict) else None
    if sources and isinstance(sources.get("base"), dict):
        return sources["base"]
    if reg.get("name"):
        return reg
    return None


def _safe_reg(search_key: str) -> Any:
    try:
        return _call_tool(
            "get_company_registration_info",
            {"searchKey": search_key},
            cli=("company", "registration-info"),
        )
    except Exception:  # noqa: BLE001
        return None


def _rank_candidates(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """优先：精确同名 > 品牌核心被包含 > 内地运营主体；降权纯英文/壳主体。"""
    q = _normalize_brand(query)

    def score(c: dict[str, Any]) -> int:
        n = str(c.get("name") or "")
        nc = _normalize_brand(n)
        s = 0
        if n == query:
            s += 200
        if q and q in nc:
            s += 60
        elif q and q in n:
            s += 50
        if re.search(r"有限公司|有限责任公司", n):
            s += 10
        if re.fullmatch(r"[A-Za-z0-9\s.,()&]+", n or ""):
            s -= 40
        return s

    return sorted(candidates, key=score, reverse=True)


def fetch_company_profile(keyword: str) -> dict[str, Any]:
    """经天眼查 MCP 拉取工商登记 + 失信摘要，带近似匹配与稀疏兜底。"""
    name = (keyword or "").strip()
    if not name:
        raise ValueError("企业名为空")

    profile: dict[str, Any] = {
        "source": "tianyancha_mcp",
        "query": name,
        "basic": None,
        "dishonest": None,
        "candidates": [],
        "ok": False,
        "message": "",
    }

    brand = _normalize_brand(name)
    # 1) 原词搜索；2) 若归一名与原名不同，额外搜品牌核心并把结果前置（优先内地运营主体）
    candidates = _safe_search(name)
    if brand and brand != name:
        candidates = _safe_search(brand) + candidates
    # 去重（按名称）并保留顺序
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for c in candidates:
        cn = c.get("name")
        if cn and cn not in seen:
            seen.add(cn)
            uniq.append(c)
    candidates = uniq

    profile["candidates"] = [
        {
            "name": c.get("name"),
            "creditCode": c.get("creditCode"),
            "id": c.get("id"),
            "regStatus": c.get("regStatus"),
        }
        for c in candidates
        if c.get("name")
    ]

    search_key = name
    base: dict[str, Any] | None = None

    def _rich(b: dict[str, Any]) -> bool:
        return bool((b.get("legalPersonName") or b.get("legalPerson")) and b.get("regCapital"))

    if candidates:
        # 依次尝试排名靠前的候选，直到拿到字段较全的工商主体（稀疏兜底）
        for cand in _rank_candidates(name, candidates)[:3]:
            key = str(cand.get("name") or name)
            reg = _safe_reg(key)
            b = _extract_base(reg)
            if b:
                base = b
                search_key = key
                if _rich(b):
                    break
    else:
        # 无候选：退化为直接按原名查询（保持旧行为）
        reg = _safe_reg(name)
        base = _extract_base(reg)
        search_key = name

    if not base:
        profile["message"] = profile.get("message") or "未查到工商主体"
        return profile

    profile["basic"] = {
        "name": base.get("name"),
        "creditCode": base.get("creditCode") or base.get("taxNumber"),
        "legalPerson": base.get("legalPersonName") or base.get("legalPerson"),
        "regStatus": base.get("regStatus"),
        "regCapital": base.get("regCapital"),
        "establishTime": base.get("estiblishTime") or base.get("establishTime"),
        "companyType": base.get("companyOrgType") or base.get("companyType"),
        "regLocation": base.get("regLocation"),
        "industry": base.get("industry"),
        "businessScope": (base.get("businessScope") or "")[:400],
        "tags": base.get("tags"),
        "socialStaffNum": base.get("socialStaffNum"),
        "phoneNumber": base.get("phoneNumber"),
    }
    profile["ok"] = True
    profile["message"] = "ok"

    try:
        dish = _call_tool(
            "get_dishonest_info",
            {"searchKey": base.get("name") or search_key},
            cli=("risk", "dishonest-info"),
        )
        items: list[dict[str, Any]] = []
        total = None
        if isinstance(dish, dict):
            total = dish.get("total") or dish.get("count")
            rows = dish.get("items") or dish.get("list") or []
            if isinstance(rows, list):
                for row in rows[:5]:
                    if isinstance(row, dict):
                        items.append(
                            {
                                "iname": row.get("iname") or row.get("name"),
                                "caseCode": row.get("caseCode") or row.get("casecode"),
                                "court": row.get("courtname") or row.get("court"),
                            }
                        )
            sources = dish.get("sources")
            if not items and isinstance(sources, dict):
                for v in sources.values():
                    if isinstance(v, dict) and isinstance(v.get("items"), list):
                        total = v.get("total", total)
                        for row in v["items"][:5]:
                            if isinstance(row, dict):
                                items.append(
                                    {
                                        "iname": row.get("iname") or row.get("name"),
                                        "caseCode": row.get("caseCode") or row.get("casecode"),
                                        "court": row.get("courtname") or row.get("court"),
                                    }
                                )
        profile["dishonest"] = {"count": total if total is not None else len(items), "items": items}
    except Exception as exc:  # noqa: BLE001
        profile["dishonest"] = {"count": None, "items": [], "error": str(exc)}

    return profile
