"""效果度量（P2 规模化前置 / RaaS 前置）。

记录研判/决策被**采纳 / 推翻 / 人工复核结论**，以及端到端耗时，
供后续效果度量（采纳率、AUC 标签回灌、RaaS 计费）使用。

落库 ``feedback_events`` 表（见 data/db.py SCHEMA）。所有写入走 INSERT，
append-only，可审计。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from bizatlas.data.db import get_connection

_VALID_ACTIONS = {
    "report_accepted",
    "report_overridden",
    "decision_accepted",
    "decision_overridden",
    "review_approve",
    "review_reject",
    "review_return",
}


def record_feedback(
    *,
    report_id: Optional[str] = None,
    company_id: Optional[str] = None,
    analyst: Optional[str] = None,
    action: str,
    decision: Optional[str] = None,
    comment: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> dict[str, Any]:
    """记录一条效果反馈事件。

    action 必须为 _VALID_ACTIONS 之一，否则抛 ValueError。
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"invalid feedback action: {action!r}; expected one of {sorted(_VALID_ACTIONS)}")
    row_id = str(uuid.uuid4())
    created = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO feedback_events "
            "(id, report_id, company_id, analyst, action, decision, comment, latency_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row_id,
                report_id,
                company_id,
                analyst,
                action,
                decision,
                comment,
                latency_ms,
                created,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": row_id, "action": action, "recorded_at": created}


def feedback_summary(limit: int = 500) -> dict[str, Any]:
    """聚合近期反馈：各 action 计数 + 采纳率（accepted/(accepted+overridden)）。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT action, COUNT(*) AS n FROM feedback_events GROUP BY action"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM feedback_events").fetchone()["n"]
    finally:
        conn.close()
    counts = {r["action"]: r["n"] for r in rows}
    accepted = counts.get("report_accepted", 0) + counts.get("decision_accepted", 0)
    overridden = counts.get("report_overridden", 0) + counts.get("decision_overridden", 0)
    adoption_rate = round(accepted / (accepted + overridden), 4) if (accepted + overridden) else None
    return {
        "total_events": total,
        "by_action": counts,
        "adoption_rate": adoption_rate,
        "note": "采纳率 = accepted/(accepted+overridden)；标签可回灌校准层做 AUC/KS 验证",
    }
