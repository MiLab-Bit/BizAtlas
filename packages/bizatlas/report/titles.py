from __future__ import annotations

from typing import Any

# 等级 → 可读结论标签（用于历史分析标题）
_GRADE_TAG = {
    "GREEN": "经营健康",
    "YELLOW": "关注预警",
    "ORANGE": "风险偏高",
    "RED": "负债不良",
    "BLACK": "重大风险",
}


def make_analysis_title(
    company: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    template_id: str,
) -> str:
    """生成历史分析可读标题，如「宏图建材集团有限公司负债不良」。"""
    company = company or {}
    risk = risk or {}
    name = str(company.get("name") or "未命名企业").strip()
    grade = str(risk.get("grade") or "").upper()
    tag = _GRADE_TAG.get(grade, "综合研判")

    if template_id == "credit_assessment":
        # 信用评估 / 背调
        return f"{name}信用背调（{tag}）"
    # 一页风险摘要
    return f"{name}{tag}"


def status_label(status: str | None, *, exported: bool = False) -> str:
    if exported or status in {"exported", "已导出"}:
        return "已导出"
    if status in {"generated", "分析完成", "ready"}:
        return "已生成"
    if status == "draft":
        return "已生成"  # 不再对外叫草稿
    return status or "已生成"
