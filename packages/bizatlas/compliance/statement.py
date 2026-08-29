"""数据授权与合规机制（读取层）。

设计要点
--------
合规声明最常见的失效方式是「文档写一套、系统跑另一套」。本模块把静态声明
（content/compliance/statement.yaml）与**运行时数据源实际启用状态**
（provider registry 健康检查）做一次对账，把差异显式暴露出来：

- declared_not_running：声明里写了、但运行时未启用的源
- running_not_declared：运行时启用了、但声明里没写的源（合规缺口，必须补声明）

这样声明就变成可核对的事实，而不是一段无法验证的文字。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings

STATEMENT_RELPATH = "compliance/statement.yaml"


def statement_path() -> Path:
    return get_settings().root / "content" / STATEMENT_RELPATH


def _load_yaml() -> dict[str, Any]:
    path = statement_path()
    if not path.exists():
        return {
            "available": False,
            "reason": "未找到合规声明文件",
            "detail": f"缺少 {STATEMENT_RELPATH}",
            "path": str(path),
        }
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": "合规声明解析失败",
            "detail": f"{type(exc).__name__}: {exc}",
            "path": str(path),
        }
    data["available"] = True
    data["path"] = str(path)
    return data


def _reconcile(declared: list[dict[str, Any]]) -> dict[str, Any]:
    """把声明中的数据源与运行时 registry 状态对账。"""
    try:
        from bizatlas.data.registry import provider_health_list

        live = provider_health_list()
    except Exception as exc:  # noqa: BLE001
        return {
            "checked": False,
            "reason": f"运行时数据源状态不可读：{type(exc).__name__}: {exc}",
        }

    live_map: dict[str, dict[str, Any]] = {}
    for p in live:
        # provider_health_list 可能返回 pydantic 模型或 dict，统一成 dict
        d = p if isinstance(p, dict) else (p.model_dump() if hasattr(p, "model_dump") else dict(p))
        pid = str(d.get("id") or "")
        if pid:
            live_map[pid] = d

    declared_map = {str(s.get("id")): s for s in declared if s.get("id")}

    enabled_live = {pid for pid, d in live_map.items() if d.get("enabled")}
    # 声明中 status: disabled 视为「已声明但不启用」
    declared_active = {
        pid for pid, s in declared_map.items() if str(s.get("status") or "") != "disabled"
    }

    running_not_declared = sorted(enabled_live - set(declared_map.keys()))
    declared_not_running = sorted(declared_active - enabled_live)

    rows = []
    for pid in sorted(set(declared_map) | set(live_map)):
        s = declared_map.get(pid) or {}
        d = live_map.get(pid) or {}
        rows.append(
            {
                "id": pid,
                "name": s.get("name") or d.get("name") or pid,
                "declared": pid in declared_map,
                "declared_status": s.get("status") or ("declared" if pid in declared_map else None),
                "runtime_enabled": bool(d.get("enabled")),
                "runtime_ok": bool(d.get("ok")),
                "runtime_message": d.get("message") or "",
                "authorization": s.get("authorization") or "",
                "contains_personal_info": s.get("contains_personal_info"),
            }
        )

    return {
        "checked": True,
        "rows": rows,
        "running_not_declared": running_not_declared,
        "declared_not_running": declared_not_running,
        "consistent": not running_not_declared,
        "note": (
            "running_not_declared 非空表示存在已启用但未在声明中披露的数据源，"
            "属合规缺口，须补充声明后再上线。"
        ),
    }


def load_compliance_statement() -> dict[str, Any]:
    data = _load_yaml()
    if not data.get("available"):
        return data
    sources = list(data.get("sources") or [])
    data["reconciliation"] = _reconcile(sources)
    data["source_count"] = len(sources)
    return data
