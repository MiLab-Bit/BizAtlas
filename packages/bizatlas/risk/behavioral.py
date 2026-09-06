"""商业行为层（D&B PAYDEX / FICO SBSS 式子评分）。

把已采集的工商/司法/合规事件映射为 0–100 风险子分（越高越危险）+ 显性驱动因子。
对标 FICO SBSS（融合征信+商业征信+财务+申请，输出 0–300 + reason codes）与 D&B PAYDEX/SER
（商业授信行为评分）的"多源行为信号 → 子分"思路。

数据铁律：仅使用已采集信号；某维度事件键完全缺失时标 N/A（不臆造），不把"未知"当"安全"。
"""
from __future__ import annotations

from typing import Any

# 维度定义：事件键（命中即风险）→ 权重 + 单次命中加分数
BEHAVIORAL_DIMS: dict[str, dict[str, Any]] = {
    "司法涉诉": {
        "events": ["裁判文书", "开庭公告", "立案信息", "法院公告", "司法案件"],
        "weight": 0.25,
        "per_hit": 35,
    },
    "被执行失信": {
        "events": ["失信被执行", "dishonest_executor", "被执行人", "限制高消费"],
        "weight": 0.30,
        "per_hit": 45,
    },
    "行政处罚": {
        "events": ["行政处罚", "环保处罚", "税务处罚"],
        "weight": 0.20,
        "per_hit": 30,
    },
    "经营异常": {
        "events": ["经营异常", "列入经营异常名录", "列入严重违法失信名单"],
        "weight": 0.15,
        "per_hit": 25,
    },
    "股权风险": {
        "events": ["股权冻结", "股权质押", "股权出质", "司法冻结"],
        "weight": 0.10,
        "per_hit": 30,
    },
}


def _count_event(events: dict[str, Any], key: str) -> int:
    v = events.get(key)
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        return 1 if v.strip() else 0
    return 0


def compute_behavioral(
    events: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """基于事件/工商信号计算商业行为风险子分。

    Args:
        events: 规则引擎/数据源产出的事件标志字典（键见 BEHAVIORAL_DIMS）。
        profile: 可选天眼查公司档案（预留，当前不强制需要）。
        meta: 可选公司元信息（行业等，预留）。

    Returns:
        {
          available: bool,
          scores: {dim: 0-100 | None},      # None 表示该维度数据缺口
          composite: float,                  # 加权综合（0-100，越高越危险）
          drivers: [ {factor, detail, weight} ],
          completeness: float,              # 已知维度占比
          data_gap: [dim, ...],
        }
    """
    events = events or {}
    scores: dict[str, float | None] = {}
    drivers: list[dict[str, Any]] = []
    known = 0
    weighted = 0.0
    total_w = 0.0

    for dim, cfg in BEHAVIORAL_DIMS.items():
        present = any(e in events for e in cfg["events"])
        if not present:
            scores[dim] = None
            continue
        known += 1
        cnt = sum(_count_event(events, e) for e in cfg["events"])
        sub = min(100.0, cfg["per_hit"] * cnt) if cnt > 0 else 0.0
        scores[dim] = round(sub, 1)
        if cnt > 0:
            drivers.append(
                {
                    "factor": dim,
                    "detail": f"{cnt} 条信号命中",
                    "weight": cfg["weight"],
                }
            )
            weighted += sub * cfg["weight"]
            total_w += cfg["weight"]

    composite = round(weighted / total_w, 1) if total_w > 0 else 0.0
    completeness = round(known / len(BEHAVIORAL_DIMS), 2)
    data_gap = [d for d, v in scores.items() if v is None]

    return {
        "available": known > 0,
        "scores": scores,
        "composite": composite,
        "drivers": sorted(drivers, key=lambda d: d["weight"], reverse=True),
        "completeness": completeness,
        "data_gap": data_gap,
    }
