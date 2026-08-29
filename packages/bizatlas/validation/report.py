"""风险评分有效性验证报告（读取层）。

为什么需要它
------------
一个风险评分如果没有回溯验证，它的分数就只是「一组权重的算术结果」，
无法回答审批人最关心的问题：这个分数区分得开好坏企业吗？能提前多久预警？

本模块把离线回溯的结果作为产品内的一等公民暴露出来，让评分有效性可被第三方查证，
而不是只写在 PPT 里。

严谨性约定
----------
1. 报告文件缺失时返回 available=false 并说明原因，**不生成任何占位数字**。
2. 报告内容原样返回，包含样本构成、方法披露与局限性，不做有利化裁剪。
3. 所有指标都必须带样本量与置信区间，单点数字不足以支撑有效性主张。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bizatlas.config import get_settings

REPORT_RELPATH = "validation/backtest_report.json"


def report_path() -> Path:
    """报告路径。与 benchmarks / fixtures 保持同一定位口径：settings.root / content。"""
    return get_settings().root / "content" / REPORT_RELPATH


def load_backtest_report() -> dict[str, Any]:
    """加载回溯验证报告。缺失或损坏时显式披露，不编造数字。"""
    path = report_path()
    if not path.exists():
        return {
            "available": False,
            "reason": "尚未生成回溯验证报告",
            "detail": (
                f"未找到 {REPORT_RELPATH}。回溯验证为离线批处理任务，"
                "需先运行回溯脚本产出报告后本接口才会返回指标。"
            ),
            "path": str(path),
            "disclosure": "在报告产出前，本系统不对评分有效性给出任何量化主张。",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": "回溯验证报告解析失败",
            "detail": f"{type(exc).__name__}: {exc}",
            "path": str(path),
            "disclosure": "报告不可读时不返回任何推测值。",
        }

    data.setdefault("available", True)
    data.setdefault("path", str(path))
    return data
