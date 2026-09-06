"""财务困境层（B-RCF v2.0.0）。

叠加银行/学界真实诊断模型，把"单看 Z-Score 不够"补齐为多维财务困境研判：

- **Altman Z''**（私营 / 通用企业，4 变量）：
      Z = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
      X1 = 营运资金 / 总资产
      X2 = 留存收益 / 总资产
      X3 = EBIT / 总资产
      X4 = 净资产 / 负债合计
      区带：<1.1 困境，1.1–2.6 灰区，>2.6 安全
- **Ohlson O-Score**（9 变量 logit → 违约概率 P）：
      O = -1.32 -0.407·X1 +6.03·X2 -1.43·X3 +0.0757·X4 -1.37·X5 +0.285·X6 -1.72·X7 -0.521·X8 -0.014·X9
- **Beneish M-Score**（8 变量 → 盈余操纵，> -1.78 疑似操纵）：
      M = -4.84 +0.92·DSRI +0.528·GMI +0.404·AQI +0.892·SGI +0.115·DEPI -0.172·SGAI +4.679·TATA -0.327·LVGI

数据铁律：缺输入即 N/A，绝不编造财报数字；Ohlson/Beneish 时序变量缺失时明确标注 partial / 缺口，
不假装算出一个高置信度结果。仅当原始报表科目或可由公开比率稳健推导时计算。
"""
from __future__ import annotations

import math
from typing import Any

# 中文报表科目名 → 内部键（兼容常见别名）
_NAME_MAP = {
    "营运资金": "wc",
    "总资产": "ta",
    "资产总计": "ta",
    "留存收益": "re",
    "息税前利润": "ebit",
    "利润总额": "ebit",
    "净资产": "equity",
    "所有者权益合计": "equity",
    "股东权益合计": "equity",
    "负债合计": "tl",
    "营业收入": "sales",
    "营业总收入": "sales",
    "净利润": "ni",
    "流动资产": "ca",
    "流动负债": "cl",
    "存货": "inv",
    "经营活动现金流量净额": "cfo",
}


# 内部键直通：数据源若直接给出这些键（Beneish 变量 / 内部缩写），无需中文映射
_DIRECT_KEYS = frozenset(
    {"wc", "ta", "re", "ebit", "equity", "tl", "sales", "ni", "ca", "cl", "inv", "cfo"}
    | {"DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "TATA", "LVGI"}
)


def _altman_zone(z: float) -> str:
    """Z'' 区带（通用/私营企业口径）。"""
    if z < 1.1:
        return "困境区"
    if z < 2.6:
        return "灰区"
    return "安全区"


def _altman_z2(raw: dict[str, float]) -> dict[str, Any] | None:
    need = ("wc", "ta", "re", "ebit", "equity", "tl")
    if not all(k in raw for k in need):
        return None
    wc, ta, re, ebit, eq, tl = (raw[k] for k in need)
    if ta == 0:
        return None
    x1 = wc / ta
    x2 = re / ta
    x3 = ebit / ta
    x4 = eq / tl if tl else 0.0
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    return {
        "z": round(z, 3),
        "variant": "Altman Z'' (4-var 通用/私营)",
        "zone": _altman_zone(z),
        "partial": False,
    }


def _ohlson(raw: dict[str, float]) -> dict[str, Any] | None:
    """横截面可计算子集（缺 t-1 时序变量时标 partial）。"""
    need = ("ta", "tl", "wc", "ca", "cl", "ni")
    if not all(k in raw for k in need):
        return None
    ta, tl, wc, ca, cl, ni = (raw[k] for k in need)
    if ta <= 0 or cl == 0 or ca == 0:
        return None
    x1 = math.log(ta) if ta > 0 else 0.0
    x2 = tl / ta
    x3 = wc / ta
    x4 = cl / ca
    x5 = ni / ta
    o = -1.32 - 0.407 * x1 + 6.03 * x2 - 1.43 * x3 + 0.0757 * x4 - 1.37 * x5
    p = 1.0 / (1.0 + math.exp(-o))
    return {
        "o_score": round(o, 3),
        "pd": round(p, 4),
        "partial": True,
        "note": "仅含横截面变量，缺 t-1 时序变量（Ohlson X6–X9），为部分估计",
    }


def _beneish(raw: dict[str, float]) -> dict[str, Any] | None:
    """标准 8 变量 Beneish。缺任一变量即 N/A（多为时序/同比变量）。"""
    need = ("DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "TATA", "LVGI")
    if not all(k in raw for k in need):
        missing = [k for k in need if k not in raw]
        return {"available": False, "missing": missing}
    dsri, gmi, aqi, sgi, depi, sgain, tata, lvgi = (raw[k] for k in need)
    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgain
        + 4.679 * tata
        - 0.327 * lvgi
    )
    return {"m_score": round(m, 3), "manipulation_suspect": m > -1.78, "partial": False}


def _altman_pd(zone: str) -> float | None:
    """Altman 区带 → 文档化违约概率先验（待真实标签用 calibration.fit 重估）。"""
    return {"困境区": 0.65, "灰区": 0.25, "安全区": 0.05}.get(zone)


def compute_distress(metrics: list[Any]) -> dict[str, Any]:
    """基于 financial_metrics 计算财务困境信号。

    Args:
        metrics: list[MetricValue]（含 name/value）。

    Returns:
        {
          available: bool,
          models: {altman?, ohlson?, beneish?},
          pd: float | None,            # 综合困境违约概率估计
          missing: list[str],          # 全局缺失的关键科目
          notes: list[str],
        }
    """
    raw: dict[str, float] = {}
    for m in metrics:
        name = getattr(m, "name", None)
        val = getattr(m, "value", None)
        if name is None or val is None:
            continue
        key = _NAME_MAP.get(name) or (name if name in _DIRECT_KEYS else None)
        if key:
            try:
                raw[key] = float(val)
            except (TypeError, ValueError):
                continue

    result: dict[str, Any] = {"available": False, "models": {}, "pd": None, "missing": [], "notes": []}

    alt = _altman_z2(raw)
    if alt is None:
        # 回退：演示库已存入的 5 变量 Altman Z（上市模型）作为 Altman 信号
        zval = next((float(m.value) for m in metrics if getattr(m, "name", "") == "Z值(Altman)" and m.value is not None), None)
        if zval is not None:
            alt = {
                "z": round(zval, 3),
                "variant": "Altman Z (5-var 上市模型，演示回退)",
                "zone": _altman_zone(zval),
                "partial": True,
            }
            result["notes"].append("未取到原始报表科目，使用已落库的 5 变量 Altman Z 作为 Altman 信号")
    if alt:
        result["models"]["altman"] = alt

    ohl = _ohlson(raw)
    if ohl:
        result["models"]["ohlson"] = ohl

    ben = _beneish(raw)
    if ben:
        if ben.get("available", True):
            result["models"]["beneish"] = ben
        else:
            # 缺时序变量时 Beneish 不可用：只记数据缺口，不进 models，
            # 避免把「不可用」算成「已覆盖」而让 available 失真。
            result["notes"].append(
                "Beneish M-Score 不可用（缺时序变量: %s）" % "、".join(ben.get("missing", []))
            )

    # 综合困境 PD：优先 Ohlson，其次 Altman 区带先验
    if ohl and ohl.get("pd") is not None:
        result["pd"] = ohl["pd"]
        result["notes"].append("PD 取自 Ohlson O-Score（部分估计）")
    elif alt and alt.get("zone"):
        pd = _altman_pd(alt["zone"])
        if pd is not None:
            result["pd"] = pd
            result["notes"].append(f"PD 取自 Altman 区带先验（{alt['zone']}）")

    # available 只认「真正算出信号的模型」：不可用模型的占位不计入，
    # 否则下游会把 pd=None 当成风险 0 参与加权（把未知当安全）。
    result["available"] = (
        result["pd"] is not None
        or bool(result["models"].get("altman"))
        or bool(result["models"].get("ohlson"))
    )
    # 全局缺失科目提示
    for k in ("wc", "ta", "re", "ebit", "equity", "tl", "ca", "cl", "ni"):
        if k not in raw:
            result["missing"].append(k)
    return result
