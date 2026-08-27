from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bizatlas.config import get_settings


def company_json_import_configured() -> bool:
    # 本地导入，无 key；目录存在即视为可用
    try:
        return Path(get_settings().company_json_dir).exists()
    except Exception:  # noqa: BLE001
        return False


# 字段别名 → 标准字段；导入包字段命名不一时仍能容错
_FIELD_ALIASES = {
    "name": ["name", "company_name", "企业名称", "名称"],
    "creditCode": ["creditCode", "credit_code", "统一社会信用代码", "taxNumber", "tax_number"],
    "legalPerson": ["legalPerson", "legal_person", "legalPersonName", "法定代表人", "法人"],
    "regStatus": ["regStatus", "reg_status", "经营状态", "登记状态"],
    "regCapital": ["regCapital", "reg_capital", "注册资本"],
    "establishTime": ["establishTime", "establish_time", "estiblishTime", "成立日期", "成立时间"],
    "companyType": ["companyType", "company_type", "companyOrgType", "企业类型"],
    "regLocation": ["regLocation", "reg_location", "注册地址", "住所"],
    "industry": ["industry", "行业", "行业门类"],
    "businessScope": ["businessScope", "business_scope", "经营范围"],
    "socialStaffNum": ["socialStaffNum", "social_staff_num", "参保人数", "员工人数"],
    "phoneNumber": ["phoneNumber", "phone_number", "联系电话"],
}


def _pick(obj: dict[str, Any], field: str) -> Any:
    for alias in _FIELD_ALIASES.get(field, [field]):
        if alias in obj and obj[alias] not in (None, ""):
            return obj[alias]
    return None


def _find_file(dir_path: Path, keyword: str) -> Path | None:
    kw = keyword.strip()
    if not kw:
        return None
    # 1) 文件名精确/包含匹配
    for p in dir_path.glob("*.json"):
        stem = p.stem
        if stem == kw or kw in stem or stem in kw:
            return p
    # 2) 文件内 name 字段匹配
    for p in dir_path.glob("*.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            nm = _pick(obj, "name")
            if nm and (nm == kw or kw in str(nm)):
                return p
    return None


def fetch_company_profile(keyword: str) -> dict[str, Any]:
    """从 COMPANY_JSON_DIR 读取本地导出的工商司法 JSON 包，返回与天眼查/企查查同构的结构。

    作为无商业 Key 时的兜底源（registry resolve_order: judicial 末位）。
    字段命名容错：常见的中英文别名均可识别。
    """
    name = (keyword or "").strip()
    if not name:
        raise ValueError("企业名为空")

    profile: dict[str, Any] = {
        "source": "company_json_import",
        "query": name,
        "basic": None,
        "dishonest": None,
        "candidates": [],
        "ok": False,
        "message": "",
    }

    dir_path = Path(get_settings().company_json_dir)
    if not dir_path.exists():
        profile["message"] = f"导入目录不存在：{dir_path}"
        return profile

    f = _find_file(dir_path, name)
    if f is None:
        profile["message"] = "未找到匹配的导出 JSON 包"
        return profile

    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        profile["message"] = f"JSON 解析失败：{exc}"
        return profile
    if not isinstance(obj, dict):
        profile["message"] = "导出 JSON 根节点非对象"
        return profile

    profile["basic"] = {
        "name": _pick(obj, "name"),
        "creditCode": _pick(obj, "creditCode"),
        "legalPerson": _pick(obj, "legalPerson"),
        "regStatus": _pick(obj, "regStatus"),
        "regCapital": _pick(obj, "regCapital"),
        "establishTime": _pick(obj, "establishTime"),
        "companyType": _pick(obj, "companyType"),
        "regLocation": _pick(obj, "regLocation"),
        "industry": _pick(obj, "industry"),
        "businessScope": (str(_pick(obj, "businessScope") or ""))[:400],
        "socialStaffNum": _pick(obj, "socialStaffNum"),
        "phoneNumber": _pick(obj, "phoneNumber"),
    }
    profile["ok"] = True
    profile["message"] = "ok"

    dish = obj.get("dishonest") or obj.get("失信") or obj.get("dishonestList")
    if isinstance(dish, list):
        profile["dishonest"] = {
            "count": len(dish),
            "items": [
                {
                    "iname": d.get("iname") or d.get("name"),
                    "caseCode": d.get("caseCode") or d.get("caseCode"),
                    "court": d.get("court") or d.get("courtname"),
                }
                for d in dish[:5]
                if isinstance(d, dict)
            ],
        }
    elif isinstance(dish, dict):
        profile["dishonest"] = {"count": dish.get("count") or dish.get("total"), "items": []}
    else:
        profile["dishonest"] = {"count": 0, "items": []}

    return profile
