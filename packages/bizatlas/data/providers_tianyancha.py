from __future__ import annotations

import json
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


def fetch_company_profile(keyword: str) -> dict[str, Any]:
    """经天眼查 MCP（tyc-cli / shared-core）拉取工商登记 + 失信摘要。"""
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

    search_key = name
    try:
        candidates = search_companies(name, limit=5)
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
        if candidates:
            pick = next((c for c in candidates if c.get("name") == name), None) or next(
                (c for c in candidates if name in str(c.get("name") or "")),
                candidates[0],
            )
            search_key = str(pick.get("name") or name)
    except Exception as exc:  # noqa: BLE001
        profile["message"] = f"搜索失败：{exc}"

    try:
        reg = _call_tool(
            "get_company_registration_info",
            {"searchKey": search_key},
            cli=("company", "registration-info"),
        )
    except Exception as exc:  # noqa: BLE001
        profile["message"] = profile.get("message") or str(exc)
        return profile

    base = None
    if isinstance(reg, dict):
        sources = reg.get("sources") if isinstance(reg.get("sources"), dict) else None
        if sources and isinstance(sources.get("base"), dict):
            base = sources["base"]
        elif reg.get("name"):
            base = reg

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
