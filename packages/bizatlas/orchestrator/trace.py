"""多 Agent 执行迹（可视化用，确定性派生）。

把 run_analysis_pipeline 的真实产出（确定性评分内核 + 4 个 Agent 信封）
收敛成前端「调查工作台」可直接渲染的结构：Agent 卡 / 工具调用卡 / 事件时间线 / 证据面板。

设计要点：
- 纯函数、零 LLM、完全离线确定性；不改动评分内核，只读取管线结果。
- 所有 Agent / 工具 / 事件都来自真实管线步骤，绝不编造「伪 Agent 协作」。
- 时间线用 seq + 累计偏移（ms）表达，前端按序回放即可，无需后端 SSE。
"""

from __future__ import annotations

from typing import Any

# Agent 中文名映射（role_key -> 展示名）
_AGENT_LABELS: dict[str, str] = {
    "scoring": "风险评分内核",
    "classifier": "分类 Agent",
    "planner": "规划 Agent",
    "researcher": "研究 Agent",
    "writer": "写作 Agent",
}

# 五维 id -> 中文（用于证据/事件可读性）
_DIM_LABELS: dict[str, str] = {
    "财务": "财务",
    "经营": "经营",
    "行业": "行业",
    "舆情": "舆情",
    "关联": "关联",
}


def _agent_card(
    *,
    role_key: str,
    status: str,
    mode: str,
    ok: bool,
    task: str,
    inputs: int,
    outputs: int,
    evidence: int,
    tool_calls: list[str],
    notes: list[str],
    summary: str = "",
) -> dict[str, Any]:
    return {
        "role_key": role_key,
        "label": _AGENT_LABELS.get(role_key, role_key),
        "status": status,  # queued|running|completed|failed|blocked|waiting_review
        "mode": mode,  # deterministic|llm|fallback
        "ok": ok,
        "task": task,
        "inputs": inputs,
        "outputs": outputs,
        "evidence": evidence,
        "tool_calls": tool_calls,
        "notes": notes,
        "summary": summary,
    }


def _tool_call(
    *,
    agent: str,
    name: str,
    kind: str,
    detail: str,
    result: str,
    ok: bool = True,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "agent_label": _AGENT_LABELS.get(agent, agent),
        "name": name,
        "kind": kind,  # rule|compute|rag|template
        "detail": detail,
        "result": result,
        "ok": ok,
    }


def build_trace(result: dict[str, Any]) -> dict[str, Any]:
    """从 run_analysis_pipeline 的 enriched 结果派生可视化执行迹。"""
    risk = result.get("risk") or {}
    company = result.get("company") or {}
    metrics_count = int(result.get("metrics_count") or 0)
    hits = risk.get("hits") or []
    rules_hit = len(hits)
    citations = result.get("citations") or []
    quality = risk.get("quality") or {}
    completeness = quality.get("completeness")
    dimensions = risk.get("dimensions") or []
    veto = risk.get("veto") or {}

    agents_dump = result.get("agents") or {}
    planner_out = (agents_dump.get("planner") or {}).get("output") or {}
    researcher_out = (agents_dump.get("researcher") or {}).get("output") or {}
    writer_out = (agents_dump.get("writer") or {}).get("output") or {}
    classifier_out = (agents_dump.get("classifier") or {}).get("output") or {}

    research_findings = researcher_out.get("findings") or []
    research_found = [f for f in research_findings if f.get("found")]
    research_gaps = [f for f in research_findings if not f.get("found")]
    data_gaps = planner_out.get("data_gaps") or []
    disclosures = writer_out.get("disclosures") or []

    graph = result.get("graph")
    stress = result.get("stress")

    # —— Agent 卡 ——
    agents: list[dict[str, Any]] = []

    # 1) 评分内核（从 core 合成，永远确定性、已完成）
    agents.append(
        _agent_card(
            role_key="scoring",
            status="completed",
            mode="deterministic",
            ok=True,
            task="规则匹配 + 五维加权评分 + 图谱/压力计算",
            inputs=metrics_count,
            outputs=rules_hit,
            evidence=len(citations),
            tool_calls=["RuleEngine.match", "score_risk", "build_guarantee_graph", "run_stress"],
            notes=[],
            summary=f"等级 {risk.get('grade')} · 危险度 {risk.get('score')}",
        )
    )

    # 2) 分类 Agent
    cls = agents_dump.get("classifier") or {}
    agents.append(
        _agent_card(
            role_key="classifier",
            status="completed" if cls.get("ok", True) else "failed",
            mode=str(cls.get("mode", "deterministic")),
            ok=bool(cls.get("ok", True)),
            task="识别行业赛道 + 路由重点核查维度",
            inputs=1 if company.get("industry") else 0,
            outputs=len(classifier_out.get("routing_hints") or []),
            evidence=len(classifier_out.get("routing_hints") or []),
            tool_calls=["classify_company"],
            notes=cls.get("notes") or [],
            summary=f"赛道 {classifier_out.get('category')}",
        )
    )

    # 3) 规划 Agent
    pln = agents_dump.get("planner") or {}
    agents.append(
        _agent_card(
            role_key="planner",
            status="completed" if pln.get("ok", True) else "failed",
            mode=str(pln.get("mode", "deterministic")),
            ok=bool(pln.get("ok", True)),
            task="枚举数据缺口 + 生成本地检索计划（失败感知）",
            inputs=metrics_count,
            outputs=len(data_gaps),
            evidence=len(planner_out.get("research_plan") or []),
            tool_calls=["plan_research"],
            notes=pln.get("notes") or [],
            summary=f"发现 {len(data_gaps)} 项数据缺口",
        )
    )

    # 4) 研究 Agent
    res = agents_dump.get("researcher") or {}
    agents.append(
        _agent_card(
            role_key="researcher",
            status="completed" if res.get("ok", True) else "failed",
            mode=str(res.get("mode", "deterministic")),
            ok=bool(res.get("ok", True)),
            task="本地 RAG 检索补充证据（缺则显式披露，绝不编造）",
            inputs=len(research_findings),
            outputs=len(research_found),
            evidence=researcher_out.get("citation_count") or 0,
            tool_calls=[f"ask_company×{len(research_findings)}"] if research_findings else [],
            notes=res.get("notes") or [],
            summary=f"命中 {len(research_found)} 维 · 缺口 {len(research_gaps)} 维",
        )
    )

    # 5) 写作 Agent
    wrt = agents_dump.get("writer") or {}
    narrative = writer_out.get("narrative") or {}
    agents.append(
        _agent_card(
            role_key="writer",
            status="completed" if wrt.get("ok", True) else "failed",
            mode=str(wrt.get("mode", "deterministic")),
            ok=bool(wrt.get("ok", True)),
            task="writer-only 叙事合成 + 披露透传（不改分）",
            inputs=len(hits) + len(research_found),
            outputs=len([v for v in narrative.values() if v]),
            evidence=len(disclosures),
            tool_calls=["write_report"],
            notes=wrt.get("notes") or [],
            summary=f"透传 {len(disclosures)} 条披露",
        )
    )

    # —— 工具调用卡（扁平）——
    tool_calls: list[dict[str, Any]] = [
        _tool_call(
            agent="scoring",
            name="RuleEngine.match",
            kind="rule",
            detail=f"对 {metrics_count} 项指标执行风险规则",
            result=f"命中 {rules_hit} 条",
        ),
        _tool_call(
            agent="scoring",
            name="score_risk",
            kind="compute",
            detail="五维加权评分（唯一事实源）",
            result=f"grade={risk.get('grade')} score={risk.get('score')}",
        ),
        _tool_call(
            agent="scoring",
            name="build_guarantee_graph",
            kind="compute",
            detail="构建担保/关联关系图谱",
            result="已生成" if graph else "无图谱数据",
            ok=bool(graph),
        ),
        _tool_call(
            agent="scoring",
            name="run_stress",
            kind="compute",
            detail="压力情景推演",
            result="已计算" if stress else "未启用",
            ok=bool(stress),
        ),
        _tool_call(
            agent="classifier",
            name="classify_company",
            kind="rule",
            detail=f"行业字段：{company.get('industry') or '（空）'}",
            result=f"赛道 {classifier_out.get('category')}",
        ),
        _tool_call(
            agent="planner",
            name="plan_research",
            kind="rule",
            detail="枚举数据缺口并生成检索提问",
            result=f"{len(data_gaps)} 项缺口 · {len(planner_out.get('research_plan') or [])} 个检索维度",
        ),
    ]
    for f in research_findings:
        tool_calls.append(
            _tool_call(
                agent="researcher",
                name="ask_company",
                kind="rag",
                detail=f"[{f.get('dimension')}] {f.get('query')}",
                result=(f.get("answer") or "")[:60] or "未检索到（缺口披露）",
                ok=bool(f.get("found")),
            )
        )
    tool_calls.append(
        _tool_call(
            agent="writer",
            name="write_report",
            kind="template",
            detail="叙事合成 + 失败感知披露透传",
            result=f"{len(disclosures)} 条披露",
        )
    )

    # —— 事件时间线（有序，seq + 累计偏移 ms，确定性回放）——
    events: list[dict[str, Any]] = []
    t = 0

    def _ev(agent: str, etype: str, message: str, level: str = "info") -> None:
        nonlocal t
        events.append(
            {
                "seq": len(events),
                "ts_offset_ms": t,
                "agent": agent,
                "agent_label": _AGENT_LABELS.get(agent, agent),
                "type": etype,
                "message": message,
                "level": level,
            }
        )

    _ev("scoring", "task_created", "研判任务创建，进入多 Agent 协作流程")
    t += 80
    _ev("scoring", "parse", f"资料解析：加载 {metrics_count} 项指标", "info" if metrics_count else "warn")
    t += 120
    _ev("scoring", "rules", f"规则评分：命中 {rules_hit} 条风险规则")
    t += 100
    if veto.get("triggered"):
        _ev("scoring", "veto", f"命中否决项：{veto.get('reason') or '重大风险'}，直接判定最高风险", "warn")
    else:
        _ev("scoring", "score", f"五维评分完成：{risk.get('grade')} / {risk.get('score')}")
    t += 90
    _ev("classifier", "classify", f"分类 Agent：识别为 {classifier_out.get('category')} 赛道，路由 {len(classifier_out.get('routing_hints') or [])} 个重点维度")
    t += 70
    _ev(
        "planner",
        "plan",
        f"规划 Agent：枚举 {len(data_gaps)} 项数据缺口",
        "warn" if data_gaps else "info",
    )
    t += 110
    _ev(
        "researcher",
        "research",
        f"研究 Agent：检索 {len(research_findings)} 个维度，命中 {len(research_found)}，缺口 {len(research_gaps)}",
        "warn" if research_gaps else "info",
    )
    t += 130
    _ev(
        "writer",
        "write",
        f"写作 Agent：合成叙事，透传 {len(disclosures)} 条披露（失败感知）",
    )
    t += 60
    _ev("scoring", "done", "研判完成，报告就绪", "info")

    # —— 证据面板（核心 citations + 检索命中，去重）——
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in citations:
        cid = str(c.get("id") or c.get("label") or len(seen))
        if cid in seen:
            continue
        seen.add(cid)
        evidence.append(
            {
                "id": cid,
                "label": c.get("label") or "",
                "dimension": "",
                "page": c.get("page"),
                "tier": c.get("tier"),
                "value": c.get("value"),
                "confidence": None,
                "source": c.get("id") or "",
                "kind": "metric",
            }
        )
    for i, f in enumerate(research_found):
        cid = f"rag-{i}"
        if cid in seen:
            continue
        seen.add(cid)
        evidence.append(
            {
                "id": cid,
                "label": (f.get("answer") or "")[:80],
                "dimension": f.get("dimension") or "",
                "page": None,
                "tier": None,
                "value": None,
                "confidence": f.get("confidence"),
                "source": f.get("query") or "",
                "kind": "rag",
            }
        )

    summary = {
        "grade": risk.get("grade"),
        "score": risk.get("score"),
        "completeness": completeness,
        "rules_hit": rules_hit,
        "data_gaps": len(data_gaps),
        "research_found": len(research_found),
        "research_gaps": len(research_gaps),
        "disclosures": len(disclosures),
        "pipeline_mode": result.get("pipeline_mode"),
        "llm_used": result.get("pipeline_mode") == "llm",
        "dimensions": dimensions,
        "headline": risk.get("headline") or "",
    }

    return {
        "task_id": result.get("task_id"),
        "company": company,
        "pipeline_status": result.get("pipeline_status", "succeeded"),
        "pipeline_mode": result.get("pipeline_mode"),
        "agents": agents,
        "tool_calls": tool_calls,
        "events": events,
        "evidence": evidence,
        "summary": summary,
    }
