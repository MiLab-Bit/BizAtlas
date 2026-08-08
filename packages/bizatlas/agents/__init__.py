"""商舆多 Agent 编排层。

- classifier：企业行业分类与路由
- planner：研究计划 + 失败感知（数据缺口枚举）
- researcher：本地 RAG 检索增强（检索为空显式披露，不编造）
- writer：writer-only 叙事发布（只叙事不评分，过 Number Gate）
- pipeline：编排上述四者 + 确定性评分内核
"""

from __future__ import annotations

from bizatlas.agents.base import AgentMode, AgentResult, Disclosure, collect_agent_mode
from bizatlas.agents.classifier import classify_company
from bizatlas.agents.pipeline import run_analysis_pipeline
from bizatlas.agents.planner import plan_research
from bizatlas.agents.researcher import research
from bizatlas.agents.writer import write_report

__all__ = [
    "AgentMode",
    "AgentResult",
    "Disclosure",
    "collect_agent_mode",
    "classify_company",
    "plan_research",
    "research",
    "write_report",
    "run_analysis_pipeline",
]
