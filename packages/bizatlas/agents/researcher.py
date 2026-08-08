"""研究 Agent：按规划在本地资料（RAG）中检索补充证据。

失败感知约定：检索无结果（未上传对应资料 / 命中为空）时，显式记录
缺口披露（gap_disclosure），**绝不**用 LLM 凭空生成"伪证据"。
检索命中的片段带页码/置信度，作为结论的可溯源引用。
"""

from __future__ import annotations

from typing import Any

from bizatlas.agents.base import AgentMode, AgentResult, Disclosure
from bizatlas.rag.simple import ask_company


def research(
    research_plan: list[dict[str, str]],
    *,
    company_id: str | None = None,
    fixture_id: str | None = None,
) -> AgentResult:
    findings: list[dict[str, Any]] = []
    gap_disclosures: list[Disclosure] = []
    citations: list[dict[str, Any]] = []
    used_llm = False

    for step in research_plan:
        dimension = step.get("dimension") or "通用"
        query = step.get("query") or ""
        try:
            rag = ask_company(query, company_id=company_id, fixture_id=fixture_id)
        except Exception:  # noqa: BLE001
            rag = None

        if not rag or not rag.get("citations"):
            # 失败感知：明确说"没检索到"，而不是编造
            gap_disclosures.append(
                Disclosure(
                    code="retrieval_gap",
                    severity="info",
                    message=f"「{dimension}」维度：本地资料未检索到相关信息（{query}），该维度暂以规则/财务指标研判为主。",
                )
            )
            findings.append(
                {
                    "dimension": dimension,
                    "query": query,
                    "answer": "",
                    "citations": [],
                    "confidence": 0.0,
                    "found": False,
                }
            )
            continue

        used_llm = used_llm or bool(rag.get("llm_used"))
        for c in rag.get("citations") or []:
            citations.append({**c, "dimension": dimension})
        findings.append(
            {
                "dimension": dimension,
                "query": query,
                "answer": rag.get("answer") or "",
                "citations": rag.get("citations") or [],
                "confidence": rag.get("confidence") or 0.0,
                "found": True,
            }
        )

    output = {
        "findings": findings,
        "unresolved": [f["query"] for f in findings if not f["found"]],
        "gap_disclosures": [g.model_dump() for g in gap_disclosures],
        "citation_count": len(citations),
    }

    mode = AgentMode.LLM if used_llm else AgentMode.DETERMINISTIC
    notes = []
    if gap_disclosures:
        notes.append(f"有 {len(gap_disclosures)} 个维度本地资料缺失，已显式披露。")

    return AgentResult(
        role="researcher",
        ok=True,
        mode=mode,
        output=output,
        citations=citations,
        notes=notes,
    )
