"""担保链违约传染推导（P1 差异化加深）。

在现有 :func:`bizatlas.kg.graph.build_guarantee_graph` 之上，把「谁为谁担保」
的拓扑变成**可量化的传染风险**：当链条上某担保方违约时，沿担保边向上穿透，
抬高核心主体的违约概率(PD)。

模型透明、零外部依赖、可审计；所有权重与假设显式写成常量。
本模块不编造任何工商事实——担保关系完全来自图谱（fixtures 或上传的 graph.json）。
"""
from __future__ import annotations

from typing import Any

from bizatlas.kg.graph import build_guarantee_graph

# 担保方节点风险标签 → 先验违约概率（文档化，待真实代偿数据校准）
_RISK_PD = {"high": 0.60, "warn": 0.30, "normal": 0.10, "self": 0.0, None: 0.10}

# 单条担保边的传染权重（代偿责任通常为部分，非全额）
_EDGE_WEIGHT = 0.5


def _node_pd(node: dict[str, Any]) -> float:
    risk = node.get("risk")
    if risk in _RISK_PD:
        return _RISK_PD[risk]
    # 兼容布尔式 dishonest 标记
    if node.get("dishonest") or node.get("risk") == "high":
        return _RISK_PD["high"]
    return _RISK_PD["normal"]


def compute_contagion(
    company_id: str,
    fixture_id: str | None = None,
    base_pd: float = 0.05,
) -> dict[str, Any]:
    """计算担保链传染。

    Returns:
        {
          nodes, edges,
          contagion_score: 0-1（链条对核心主体 PD 的额外抬升贡献）,
          direct_exposure: 直接担保方数量,
          affected: [{id, name, risk, node_pd, contributes}],
          note
        }
    """
    g = build_guarantee_graph(company_id, fixture_id=fixture_id)
    nodes = g.get("nodes", [])
    edges = g.get("edges", [])

    # 建邻接：下游(direction target) 对上游(source) 的传染贡献
    # 简化处理：按边权重 × 下游节点 PD 求和（线性近似，单层；
    # 多跳已在图谱合成时压平为链式，故足够）。
    by_id = {n.get("id"): n for n in nodes}
    affected: list[dict[str, Any]] = []
    contributions: list[float] = []
    direct_exposure = 0
    for e in edges:
        src, dst = e.get("source"), e.get("target")
        child = by_id.get(dst) or by_id.get(src)
        if not child:
            continue
        p = _node_pd(child)
        rel = e.get("rel", "担保")
        is_direct = src == nodes[0].get("id") if nodes else False
        if is_direct:
            direct_exposure += 1
        # 一阶近似：effort = weight * node_pd
        contrib = round(_EDGE_WEIGHT * p, 4)
        contributions.append(contrib)
        affected.append(
            {
                "id": child.get("id"),
                "name": child.get("name"),
                "risk": child.get("risk"),
                "node_pd": round(p, 4),
                "rel": rel,
                "direct": bool(is_direct),
                "contributes": contrib,
            }
        )

    # 传染得分：各独立传染源以「至少一条触发」计 —— 1 - Π(1 - c_i)
    survive = 1.0
    for c in contributions:
        survive *= 1.0 - min(1.0, c)
    contagion_score = round(1.0 - survive, 4)

    return {
        "nodes": nodes,
        "edges": edges,
        "base_pd": base_pd,
        "contagion_score": contagion_score,
        "direct_exposure": direct_exposure,
        "affected": affected,
        "note": (
            "传染得分为沿担保边的线性近似：1-Π(1-wᵢ·PDᵢ)，"
            "wᵢ=%.2f（部分代偿假设）。图谱来自 fixtures/graph.json，非工商实扫时为演示合成。"
            % _EDGE_WEIGHT
        ),
    }


def contagion_adjusted_pd(base_pd: float, contagion_score: float) -> float:
    """把担保链传染叠加到核心主体基础 PD 上（取并集，封顶 1）。"""
    return round(min(1.0, 1.0 - (1.0 - base_pd) * (1.0 - contagion_score)), 4)
