"""贷前授信准入决策（Pre-lending Credit Admission Decision）。

场景聚焦说明
------------
BizAtlas 的通用能力是「企业经营与风险研判」，但通用研判不构成一个可被验收的业务动作。
本模块把研判结果收敛到贷前审批场景下的**一个具体决策**：这笔授信申请是否准入、
以什么条件准入、建议额度区间是多少、是否必须转人工终审。

设计原则（与「结果可验证 / 不做绝对化承诺」对齐）
------------------------------------------------
1. 决策档位、额度系数、条件触发全部由确定性规则计算，不经过 LLM。
   相同输入必然得到相同输出，可复算、可审计、可回溯。
2. 数据不足不给额度。completeness 未达门槛直接返回 INSUFFICIENT_DATA，
   避免贷前审批中最典型的误判——把「没查到」当成「没问题」。
3. 一票否决项（失信被执行 / 破产重整迹象）直接 DECLINE，不参与加权抵消，
   不允许被其他维度的良好表现稀释。
4. 每个额度系数与每条附加条件都带 basis / trigger 字段，说明它由什么触发，
   审批人可以逐条复核，而不是面对一个无法追问的黑箱分数。
5. 输出仅为**授信建议**，不构成放款承诺；ORANGE 及以上强制人工终审。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------- 决策档位

DECISION_APPROVE = "APPROVE"
DECISION_CONDITIONAL = "APPROVE_WITH_CONDITIONS"
DECISION_MANUAL = "MANUAL_REVIEW"
DECISION_DECLINE = "DECLINE"
DECISION_INSUFFICIENT = "INSUFFICIENT_DATA"

DECISION_LABEL = {
    DECISION_APPROVE: "建议准入",
    DECISION_CONDITIONAL: "附条件准入",
    DECISION_MANUAL: "转人工审批",
    DECISION_DECLINE: "建议拒绝",
    DECISION_INSUFFICIENT: "数据不足·不予评级",
}

# 评级 -> 决策档位 / 额度系数区间 / 风险溢价(bps) / 是否强制人工
# 额度系数相对「申请额度」，例如 (0.5, 0.8) 表示建议批复申请额的 50%~80%。
GRADE_POLICY: dict[str, dict[str, Any]] = {
    "GREEN": {
        "decision": DECISION_APPROVE,
        "ratio": (0.80, 1.00),
        "premium_bps": (0, 40),
        "manual": False,
        "basis": "五维加权得分 <20，未命中否决项，偿债与现金流指标处于健康区间",
    },
    "YELLOW": {
        "decision": DECISION_CONDITIONAL,
        "ratio": (0.50, 0.80),
        "premium_bps": (40, 110),
        "manual": False,
        "basis": "五维加权得分 20~40，存在可控瑕疵，需以条件对冲后准入",
    },
    "ORANGE": {
        "decision": DECISION_MANUAL,
        "ratio": (0.20, 0.50),
        "premium_bps": (110, 240),
        "manual": True,
        "basis": "五维加权得分 40~60，风险显著，机器不作最终判断，强制转人工终审",
    },
    "RED": {
        "decision": DECISION_DECLINE,
        "ratio": (0.00, 0.20),
        "premium_bps": (240, 400),
        "manual": True,
        "basis": "五维加权得分 60~80，风险严重，建议拒绝；如需特批须走上级授权通道",
    },
    "BLACK": {
        "decision": DECISION_DECLINE,
        "ratio": (0.00, 0.00),
        "premium_bps": (0, 0),
        "manual": True,
        "basis": "命中一票否决项或得分 ≥80，不进入额度测算",
    },
    "UNRATED": {
        "decision": DECISION_INSUFFICIENT,
        "ratio": (0.00, 0.00),
        "premium_bps": (0, 0),
        "manual": True,
        "basis": "有效指标不足评级门槛，按「未知≠安全」处理，不给出额度建议",
    },
}

# 贷前授信必备核心指标（口径与 content/rules 中的指标名严格一致）
CORE_METRICS: list[str] = [
    "资产负债率",
    "流动比率",
    "速动比率",
    "利息保障倍数",
    "经营现金流/净利润",
    "ROE",
    "对外担保比例",
    "股权质押率",
]

# 补充指标：影响条件生成，但不计入准入门槛
EXTENDED_METRICS: list[str] = [
    "毛利率",
    "客户集中度",
    "供应商集中度",
    "关联交易占比",
    "担保链层级",
    "商誉占比",
    "产能利用率",
    "行业营收增速",
]

# 维度 -> 附加条件模板。命中该维度的规则时生成对应条件。
DIMENSION_CONDITIONS: dict[str, list[dict[str, str]]] = {
    "财务": [
        {"id": "FIN-01", "text": "追加不低于批复额度 30% 的抵质押物或第三方连带责任保证"},
        {"id": "FIN-02", "text": "按季报送经审计财务报表，资产负债率超约定阈值触发提前收贷条款"},
    ],
    "关联": [
        {"id": "REL-01", "text": "披露全部对外担保与关联往来明细，新增对外担保须事前书面报备"},
        {"id": "REL-02", "text": "约定担保圈解链时间表，存续期内对外担保比例不得上升"},
    ],
    "经营": [
        {"id": "OPR-01", "text": "设置单一客户回款集中度上限，超限部分不计入可用额度"},
        {"id": "OPR-02", "text": "应收账款质押并按月报送账龄结构"},
    ],
    "舆情": [
        {"id": "PUB-01", "text": "按月报送重大诉讼与行政处罚进展，新增立案即触发额度冻结复评"},
    ],
    "行业": [
        {"id": "IND-01", "text": "按行业下行情景做敏感性复评，触发阈值时重新核定额度"},
    ],
}


# ---------------------------------------------------------------- 工具函数


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _metric_index(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """按指标名建索引，取每个指标的数值（同名多条取第一条，与评分引擎一致）。"""
    idx: dict[str, Any] = {}
    for m in metrics or []:
        name = str(m.get("name") or "").strip()
        if name and name not in idx:
            idx[name] = m
    return idx


def _analyze_guarantee_contagion(
    graph: dict[str, Any] | None,
    metric_idx: dict[str, Any],
) -> dict[str, Any]:
    """担保圈风险传染暴露度。

    这是与通用「单体企业打分」类产品的关键差异：授信主体自身指标干净，
    但如果它处在一条含失信节点的担保链上，代偿风险会穿透过来。
    单体评分看不见这层，担保图谱能看见。
    """
    nodes = list((graph or {}).get("nodes") or [])
    edges = list((graph or {}).get("edges") or [])
    related = max(0, len(nodes) - 1)  # 除自身以外的关联方

    # 图谱中是否存在失信/被执行标记节点
    dishonest_nodes = [
        str(n.get("name") or n.get("id"))
        for n in nodes
        if str(n.get("risk") or "") in {"dishonest", "失信", "被执行"}
        or "失信" in str(n.get("category") or "")
    ]

    # 担保链层级：优先取指标口径，缺失时用图谱边数近似并标注来源
    depth_metric = metric_idx.get("担保链层级")
    if depth_metric is not None and depth_metric.get("value") is not None:
        try:
            depth = float(depth_metric.get("value"))
            depth_source = "指标口径「担保链层级」"
        except (TypeError, ValueError):
            depth, depth_source = float(len(edges)), "图谱边数近似（指标值非数值）"
    else:
        depth, depth_source = float(len(edges)), "图谱边数近似（指标缺失）"

    guar_ratio = None
    gm = metric_idx.get("对外担保比例")
    if gm is not None and gm.get("value") is not None:
        try:
            guar_ratio = float(gm.get("value"))
        except (TypeError, ValueError):
            guar_ratio = None

    # 暴露等级：只依据可得证据判定，证据不足则标 unknown 而非 low
    if dishonest_nodes:
        level, level_note = "high", "担保链上存在失信/被执行标记主体，代偿风险可穿透至授信主体"
    elif depth >= 3 or (guar_ratio is not None and guar_ratio > 0.50):
        level, level_note = "elevated", "担保链层级较深或对外担保比例偏高，存在连带代偿敞口"
    elif depth >= 1 or (guar_ratio is not None and guar_ratio > 0):
        level, level_note = "moderate", "存在对外担保敞口，规模可控"
    elif not nodes or related == 0:
        level, level_note = "unknown", "未取得担保关系数据，无法判断传染敞口（未知不等于无敞口）"
    else:
        level, level_note = "low", "未发现对外担保敞口"

    return {
        "exposure_level": level,
        "exposure_note": level_note,
        "chain_depth": depth,
        "chain_depth_source": depth_source,
        "related_parties": related,
        "guarantee_ratio": guar_ratio,
        "dishonest_in_chain": dishonest_nodes,
        "graph_note": (graph or {}).get("note", ""),
    }


def _contagion_haircut(contagion: dict[str, Any]) -> tuple[float, str | None]:
    """担保圈传染对额度的折减系数。返回 (折减比例, 依据)。"""
    level = contagion.get("exposure_level")
    if level == "high":
        return 0.30, "担保链含失信主体，按代偿穿透风险折减 30%"
    if level == "elevated":
        return 0.15, "担保链层级深或对外担保比例偏高，折减 15%"
    if level == "unknown":
        return 0.10, "担保关系数据缺失，按不确定性审慎折减 10%"
    return 0.0, None


def _build_conditions(
    hits: list[dict[str, Any]],
    completeness: float,
    missing_core: list[str],
    conflicts: list[dict[str, Any]],
    contagion: dict[str, Any],
) -> list[dict[str, Any]]:
    """生成附加条件。每条都带 trigger，说明它由哪条证据触发。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1) 按命中规则的维度与严重度生成
    by_dim: dict[str, list[dict[str, Any]]] = {}
    for h in hits or []:
        dim = str(h.get("dimension") or "").strip()
        if dim:
            by_dim.setdefault(dim, []).append(h)

    for dim, dim_hits in by_dim.items():
        templates = DIMENSION_CONDITIONS.get(dim) or []
        has_high = any(str(h.get("severity")) == "高" for h in dim_hits)
        # 高危维度给全部条件，中低危只给第一条
        picked = templates if has_high else templates[:1]
        trigger_rules = [
            f"{h.get('rule_id')}·{h.get('name') or h.get('message') or ''}".strip("·")
            for h in dim_hits[:3]
        ]
        for t in picked:
            if t["id"] in seen:
                continue
            seen.add(t["id"])
            out.append(
                {
                    "id": t["id"],
                    "dimension": dim,
                    "text": t["text"],
                    "severity": "高" if has_high else "中",
                    "trigger": f"{dim}维度命中 {len(dim_hits)} 条规则：" + "；".join(trigger_rules),
                }
            )

    # 2) 担保圈传染专项条件
    if contagion.get("dishonest_in_chain"):
        out.append(
            {
                "id": "CTG-01",
                "dimension": "关联",
                "text": "在放款前完成担保链失信主体的代偿敞口测算，并要求剥离或提供反担保",
                "severity": "高",
                "trigger": "担保链上存在失信/被执行主体："
                + "、".join(contagion["dishonest_in_chain"][:5]),
            }
        )
    elif contagion.get("exposure_level") in {"elevated"}:
        out.append(
            {
                "id": "CTG-02",
                "dimension": "关联",
                "text": "存续期内对外担保余额设置上限，超限须重新提交审批",
                "severity": "中",
                "trigger": f"担保链层级 {contagion.get('chain_depth')}"
                f"（{contagion.get('chain_depth_source')}）",
            }
        )

    # 3) 数据完整度不足 —— 补充材料，而不是默认通过
    if missing_core:
        out.append(
            {
                "id": "DAT-01",
                "dimension": "数据",
                "text": "补齐以下核心指标后方可进入终审：" + "、".join(missing_core),
                "severity": "高" if completeness < 0.5 else "中",
                "trigger": f"核心指标完整度 {completeness:.0%}，缺失 {len(missing_core)} 项",
            }
        )

    # 4) 多源冲突 —— 交人工核实，机器不自行裁定哪个源对
    if conflicts:
        fields = "、".join(
            str(c.get("name") or c.get("metric") or c.get("field") or "未命名字段")
            for c in conflicts[:5]
        )
        out.append(
            {
                "id": "DAT-02",
                "dimension": "数据",
                "text": f"以下字段存在多源数据冲突，须人工核实口径后采信：{fields}",
                "severity": "中",
                "trigger": f"检测到 {len(conflicts)} 处跨源冲突，系统不自动裁定优先源",
            }
        )

    return out


# ---------------------------------------------------------------- 主入口


def _attach_calibration(analyze_result: dict[str, Any], applied_amount: float | None) -> dict[str, Any]:
    """把启发式研判结果做 PD/LGD/EAD/EL 校准（见 bizatlas.risk.calibration）。"""
    from bizatlas.risk.calibration import calibrate

    risk = analyze_result.get("risk") or {}
    cal = calibrate(risk, applied_amount=applied_amount)
    return {
        "pd": cal.pd,
        "lgd": cal.lgd,
        "ead": cal.ead,
        "expected_loss": cal.expected_loss,
        "calibrated_grade": cal.calibrated_grade,
        "rationale": cal.rationale,
    }


def build_credit_decision(
    analyze_result: dict[str, Any],
    *,
    applied_amount: float | None = None,
    tenor_months: int | None = None,
    product: str = "流动资金贷款",
) -> dict[str, Any]:
    """把 run_analyze 的研判结果转成贷前授信准入决策。

    Args:
        analyze_result: run_analyze 的返回体。
        applied_amount: 申请额度（万元）。缺省时只给系数区间，不给绝对金额。
        tenor_months: 申请期限（月），仅用于条件生成与展示。
        product: 授信产品名，仅用于展示。
    """
    risk = analyze_result.get("risk") or {}
    grade = str(risk.get("grade") or "UNRATED").upper()
    score = float(risk.get("score") or 0.0)
    quality = risk.get("quality") or {}
    veto = risk.get("veto") or {}
    hits = list(risk.get("hits") or [])
    metrics = list(analyze_result.get("metrics") or [])
    conflicts = list(analyze_result.get("conflicts") or [])
    graph = analyze_result.get("graph")
    company = analyze_result.get("company") or {}

    policy = GRADE_POLICY.get(grade) or GRADE_POLICY["UNRATED"]
    metric_idx = _metric_index(metrics)

    # --- 数据完整度：按贷前授信核心指标口径单独核算 ---
    present_core = [m for m in CORE_METRICS if m in metric_idx]
    missing_core = [m for m in CORE_METRICS if m not in metric_idx]
    core_completeness = round(len(present_core) / len(CORE_METRICS), 4)
    engine_completeness = float(quality.get("completeness") or 0.0)

    # --- 担保圈传染 ---
    contagion = _analyze_guarantee_contagion(graph, metric_idx)
    haircut, haircut_basis = _contagion_haircut(contagion)

    # --- 决策档位 ---
    decision = policy["decision"]
    manual_required = bool(policy["manual"])
    decision_reasons: list[str] = [policy["basis"]]

    # 核心指标完整度门槛：低于 50% 一律不予评级（未知≠安全）
    if core_completeness < 0.50 and not veto.get("triggered"):
        decision = DECISION_INSUFFICIENT
        manual_required = True
        decision_reasons.append(
            f"贷前核心指标完整度仅 {core_completeness:.0%}（低于 50% 门槛），"
            f"缺失 {len(missing_core)} 项，不足以支撑授信判断"
        )

    # 一票否决优先级最高
    if veto.get("triggered"):
        decision = DECISION_DECLINE
        manual_required = True
        decision_reasons.append(f"命中一票否决项：{veto.get('reason')}，不参与加权抵消")

    # 担保链含失信主体：即使自身评级尚可，也必须转人工
    if contagion.get("dishonest_in_chain") and decision in {
        DECISION_APPROVE,
        DECISION_CONDITIONAL,
    }:
        decision = DECISION_MANUAL
        manual_required = True
        decision_reasons.append(
            "担保链上存在失信/被执行主体，代偿风险可穿透，单体指标健康不足以免除人工复核"
        )

    # 多源冲突未裁定：不降档，但强制人工核实口径
    if conflicts and decision == DECISION_APPROVE:
        decision = DECISION_CONDITIONAL
        decision_reasons.append(
            f"存在 {len(conflicts)} 处多源数据冲突，系统不自动选择采信源，转为附条件准入"
        )

    # --- 额度测算 ---
    ratio_lo, ratio_hi = policy["ratio"]
    ratio_lo = _clamp(ratio_lo * (1 - haircut))
    ratio_hi = _clamp(ratio_hi * (1 - haircut))
    if decision in {DECISION_DECLINE, DECISION_INSUFFICIENT}:
        ratio_lo = ratio_hi = 0.0

    limit: dict[str, Any] = {
        "currency": "CNY",
        "unit": "万元",
        "applied_amount": applied_amount,
        "ratio_min": round(ratio_lo, 4),
        "ratio_max": round(ratio_hi, 4),
        "suggested_min": round(applied_amount * ratio_lo, 2) if applied_amount else None,
        "suggested_max": round(applied_amount * ratio_hi, 2) if applied_amount else None,
        "haircut": round(haircut, 4),
        "haircut_basis": haircut_basis,
        "basis": policy["basis"],
        "note": (
            "额度系数由评级档位与担保圈折减确定性计算得出，未使用大模型；"
            "未提供申请额度时仅给出系数区间"
        ),
    }

    prem_lo, prem_hi = policy["premium_bps"]
    pricing = {
        "risk_premium_bps_min": prem_lo,
        "risk_premium_bps_max": prem_hi,
        "note": "风险溢价为基于评级档位的建议区间，最终定价由业务政策与资金成本决定",
    }

    conditions = _build_conditions(hits, core_completeness, missing_core, conflicts, contagion)

    return {
        "scenario": "贷前审批·授信准入",
        "product": product,
        "company": {
            "id": analyze_result.get("risk", {}).get("company_id")
            or company.get("id")
            or company.get("name"),
            "name": company.get("name") or company.get("id"),
            "industry": company.get("industry") or "",
        },
        "application": {
            "applied_amount": applied_amount,
            "tenor_months": tenor_months,
            "unit": "万元",
        },
        "decision": decision,
        "decision_label": DECISION_LABEL.get(decision, decision),
        "decision_reasons": decision_reasons,
        "risk_grade": grade,
        "risk_score": score,
        "manual_gate": {
            "required": manual_required,
            "reason": (
                "ORANGE 及以上、命中否决项、担保链含失信主体、核心数据不足——"
                "以上任一情形均由人工终审，系统不作最终授信结论"
                if manual_required
                else "评级与数据完整度均达自动化通过门槛，仍可由审批人主动复核"
            ),
            "approver_role": "reviewer",
        },
        "limit": limit,
        "pricing_hint": pricing,
        "conditions": conditions,
        "guarantee_contagion": contagion,
        "veto": veto,
        "data_completeness": {
            "core_score": core_completeness,
            "core_present": present_core,
            "core_missing": missing_core,
            "engine_completeness": engine_completeness,
            "threshold": 0.50,
            "disclosure": (
                f"贷前核心指标 {len(present_core)}/{len(CORE_METRICS)} 项可得。"
                + (
                    "缺失项已在附加条件中列为补件要求，缺失不按有利于申请人的方向解释。"
                    if missing_core
                    else "核心指标齐备。"
                )
            ),
        },
        "conflicts": conflicts,
        "evidence_refs": list(risk.get("evidence_refs") or []),
        "citations": list(analyze_result.get("citations") or []),
        "calibration": _attach_calibration(analyze_result, applied_amount),
        "scoring_snapshot": risk.get("scoring") or {},
        "determinism": {
            "llm_used": False,
            "note": "决策档位、额度系数、附加条件均由规则确定性计算，同一输入可复算出同一结果",
        },
        "disclaimer": (
            "本结果为授信辅助建议，不构成放款承诺或投资建议。"
            "评级与额度基于提交时点可得数据计算，数据更新后结论可能变化；"
            "最终授信决策与责任由审批人及授信机构承担。"
        ),
    }
