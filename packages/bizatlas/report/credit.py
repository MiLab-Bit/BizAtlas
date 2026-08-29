from __future__ import annotations

from typing import Any

from bizatlas.report.onepager import build_onepager
from bizatlas.report.titles import make_analysis_title


def build_credit_assessment(
    *,
    company: dict[str, Any],
    risk: dict[str, Any],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    one = build_onepager(company=company, risk=risk, metrics_count=len(metrics))
    hits = risk.get("hits") or []
    analysis_title = make_analysis_title(company, risk, "credit_assessment")
    return {
        "template_id": "credit_assessment",
        "title": "企业信用评估报告",
        "analysis_title": analysis_title,
        "company": one["company"],
        "headline": one["headline"],
        "grade": one["grade"],
        "score": one["score"],
        "sections": [
            {
                "id": "summary",
                "title": "1. 报告摘要",
                "body": one["headline"],
                "bullets": [
                    f"风险等级：{one['grade']}",
                    f"综合危险度：{one['score']}",
                    f"规则命中：{len(hits)} 条",
                ],
            },
            {
                "id": "profile",
                "title": "2. 企业概况",
                "body": f"{company.get('name')}（{company.get('industry') or '行业未标注'}）",
                "bullets": [f"企业 ID：{company.get('id')}"],
            },
            {
                "id": "financial",
                "title": "3. 财务与经营指标",
                "body": "以下数值来自抽取/计算管线，非模型编造。",
                "bullets": [
                    f"{m.get('name')} = {m.get('value')}（{m.get('tier', '')}）"
                    for m in metrics[:20]
                ],
            },
            {
                "id": "risk",
                "title": "4. 风险研判",
                "body": "五维得分与规则命中明细。",
                "bullets": [
                    *[f"{d.get('id')}: {d.get('score')}" for d in one.get("dimensions") or []],
                    *[
                        f"[{h.get('severity')}] {h.get('message')} · {h.get('explain')}"
                        for h in hits[:12]
                    ],
                ],
            },
            {
                "id": "suggest",
                "title": "5. 授信建议（辅助）",
                "body": "仅供人工复核，不构成最终授信决策。",
                "bullets": _suggest_bullets(one["grade"], risk.get("veto") or {}),
            },
            {
                "id": "appendix",
                "title": "6. 附录：数据质量",
                "body": one.get("disclaimer") or "",
                "bullets": [
                    f"指标数：{one['data_quality'].get('metrics_count')}",
                    f"完整度：{one['data_quality'].get('completeness')}",
                    f"层级：{one['data_quality'].get('tier_mix')}",
                ],
            },
        ],
        "onepager": one,
    }


def _suggest_bullets(grade: str, veto: dict[str, Any]) -> list[str]:
    if veto.get("triggered"):
        return [f"一票否决：{veto.get('reason')}", "建议暂缓推进并升级复核"]
    mapping = {
        "GREEN": ["可正常推进", "保持常规贷后监控"],
        "YELLOW": ["可推进但需关注指标波动", "建议提高监控频率"],
        "ORANGE": ["建议补充增信材料", "审慎审批并限定用途"],
        "RED": ["建议审慎/否决或大幅压降额度", "必须完成人工尽调补强"],
        "BLACK": ["建议立即上报并停止新增敞口"],
    }
    return mapping.get(grade, ["请人工复核后决策"])
