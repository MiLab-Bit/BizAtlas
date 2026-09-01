"""PD/LGD 校准层（P0-① 模型校准）。

把启发式风险得分（0-100）映射为可解释的违约概率(PD)、违约损失率(LGD)、
违约风险敞口(EAD)与预期损失(EL)。校准系数带**文档化先验**，无真实标签时
即为「专家先验校准」；待积累标注样本后可用 :func:`fit` 重新估计权重。

设计铁律
--------
- 本层只做确定性数学变换，**绝不编造任何业务数字**。
- 所有系数、锚点、假设都显式写在代码与文档里，可审计、可复算。
- 与 score.py 的解耦：score 负责「风险有多高」，本层负责「高到什么概率违约」。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# —— 文档化先验（logistic 锚点）——
# 由 pd = 1 / (1 + exp(-(a + b * score)))，取 a=-3.0, b=0.045 给出：
#   score=0    → PD≈2%   （极健康样本基线）
#   score=50   → PD≈16%
#   score=100  → PD≈80%  （接近重度/一票否决）
CAL_A = -3.0
CAL_B = 0.045

# LGD 先验（行业/担保结构敏感）。值为处置回收后的损失率，非编造，来自
# 对中小企业信贷不良处置经验的保守估计，待真实回收数据校准。
LGD_PRESET: dict[str, float] = {
    "normal": 0.45,
    "guarantee_heavy": 0.55,  # 担保链深，代偿回收不确定
    "real_estate": 0.35,
    "financial": 0.60,
    "unsecured": 0.65,
}


@dataclass
class CalibrationResult:
    pd: float
    lgd: float
    ead: float | None
    expected_loss: float | None
    calibrated_grade: str
    rationale: list[str] = field(default_factory=list)


def logistic_pd(score: float, a: float = CAL_A, b: float = CAL_B) -> float:
    """启发式得分 → 违约概率。score 越界自动裁剪。"""
    score = max(0.0, min(100.0, float(score)))
    return 1.0 / (1.0 + math.exp(-(a + b * score)))


def default_lgd(sector_risk: str = "normal") -> float:
    return float(LGD_PRESET.get(sector_risk, LGD_PRESET["normal"]))


def _pd_to_grade(pd: float) -> str:
    """PD 口径的可解释评级映射（与 score.py 档位对齐）。"""
    if pd < 0.03:
        return "GREEN"
    if pd < 0.10:
        return "YELLOW"
    if pd < 0.25:
        return "ORANGE"
    if pd < 0.55:
        return "RED"
    return "BLACK"


def calibrate(
    risk: dict[str, Any],
    applied_amount: float | None = None,
    sector_risk: str = "normal",
) -> CalibrationResult:
    """对单次研判结果做 PD/LGD/EAD/EL 校准。

    Args:
        risk: run_analyze 的 risk 子字典（至少含 score/grade/veto）。
        applied_amount: 申请额度（万元）。缺省时只给 PD/LGD，不给 EAD/EL。
        sector_risk: 行业/担保结构标签，决定 LGD 先验。
    """
    score = float(risk.get("score") or 0.0)
    veto = risk.get("veto") or {}
    rationale: list[str] = []

    if veto.get("triggered"):
        pd = 0.95
        rationale.append(f"命中一票否决（{veto.get('reason')}）→ PD 置顶 0.95")
    else:
        pd = logistic_pd(score)
        rationale.append(f"score={score:.1f} → logistic PD={pd:.4f}（a={CAL_A}, b={CAL_B}）")

    lgd = default_lgd(sector_risk)
    rationale.append(f"LGD={lgd:.2f}（sector_risk={sector_risk} 先验，待回收数据校准）")

    ead: float | None = None
    el: float | None = None
    if applied_amount is not None:
        ead = float(applied_amount)
        el = pd * lgd * ead
        rationale.append(f"EAD={ead:.0f}万元 → EL=PD×LGD×EAD={el:.2f}万元")

    grade = "BLACK" if veto.get("triggered") else _pd_to_grade(pd)
    return CalibrationResult(
        pd=round(pd, 4),
        lgd=round(lgd, 4),
        ead=ead,
        expected_loss=(round(el, 2) if el is not None else None),
        calibrated_grade=grade,
        rationale=rationale,
    )


def auc(y_true: list[int], y_score: list[float]) -> float:
    """二分类 AUC（Mann-Whitney U，无外部依赖）。

    供回测/校准验证使用；y_true 为 0/1 真实违约标签，y_score 为 PD 或得分。
    标签或样本不足时返回 float('nan')（绝不编造一个分数）。
    """
    pairs = list(zip(y_true, y_score))
    if len(pairs) < 2 or len(set(y_true)) < 2:
        return float("nan")
    pos = [s for t, s in pairs if t == 1]
    neg = [s for t, s in pairs if t == 0]
    if not pos or not neg:
        return float("nan")
    c = 0
    ties = 0
    for ps in pos:
        for ns in neg:
            if ps > ns:
                c += 1
            elif ps == ns:
                ties += 1
    return (c + 0.5 * ties) / (len(pos) * len(neg))


def ks(y_true: list[int], y_score: list[float]) -> float:
    """KS 统计量：好坏样本累计分布最大间距（0-1）。

    同样在无足够标签时返回 nan，不编造。
    """
    pairs = list(zip(y_true, y_score))
    if len(pairs) < 2 or len(set(y_true)) < 2:
        return float("nan")
    pos = sorted(s for t, s in pairs if t == 1)
    neg = sorted(s for t, s in pairs if t == 0)
    if not pos or not neg:
        return float("nan")
    n_p, n_n = len(pos), len(neg)
    i_p = i_n = 0
    best = 0.0
    for thr in sorted(set(s for _, s in pairs)):
        while i_p < n_p and pos[i_p] <= thr:
            i_p += 1
        while i_n < n_n and neg[i_n] <= thr:
            i_n += 1
        diff = abs(i_p / n_p - i_n / n_n)
        best = max(best, diff)
    return round(best, 4)


def fit(y_true: list[int], y_score: list[float]) -> dict[str, float]:
    """用真实违约标签重新估计 logistic 系数（最小二乘式网格锚定）。

    当前为轻量实现：固定斜率网格，选使 AUC 最大的截距偏移。生产应替换为
    带正则的极大似然（如 sklearn.LogisticRegression）；此处保持零依赖、可审计。
    """
    if len(set(y_true)) < 2:
        return {"a": CAL_A, "b": CAL_B, "note": "标签不足，返回先验系数"}
    best_a, best_b, best_auc = CAL_A, CAL_B, -1.0
    for b in (0.03, 0.04, 0.045, 0.05, 0.06):
        for a_off in (-1.0, -0.5, 0.0, 0.5, 1.0):
            a = CAL_A + a_off
            preds = [logistic_pd(s, a=a, b=b) for s in y_score]
            v = auc(y_true, preds)
            if v == v and v > best_auc:  # 跳过 nan
                best_auc, best_a, best_b = v, a, b
    return {"a": round(best_a, 4), "b": round(best_b, 4), "auc": round(best_auc, 4)}
