"""多 Agent 编排的基础类型与护栏。

设计原则（对齐商舆"数据+规则+计算"内核）：
- 确定性评分（run_analyze）是**唯一**事实源；任何 Agent 不得改分。
- 每个 Agent 不论是否用到 LLM，统一返回 AgentResult 信封，离线（无 key）时
  走确定性/模板降级，保证测试与断网环境可用。
- Disclosure 显式承载"失败感知"：系统不知道/不完整之处必须说出来，绝不默默填补。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentMode(str, Enum):
    DETERMINISTIC = "deterministic"  # 纯规则/模板，未用 LLM
    LLM = "llm"  # 经 LLM 增强
    FALLBACK = "fallback"  # LLM 调用失败或不可用，回退模板


class AgentResult(BaseModel):
    """统一的 Agent 产出信封。"""

    role: str
    ok: bool = True
    mode: AgentMode = AgentMode.DETERMINISTIC
    output: Any = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class Disclosure(BaseModel):
    """失败感知单元：显式披露系统'不知道/不完整/已降级'之处。

    这些单元会透传到最终报告，确保'缺数据'被看见而不是被编造掩盖。
    """

    code: str
    severity: str = "info"  # info | warn
    message: str


def collect_agent_mode(*results: AgentResult) -> AgentMode:
    """汇总多个 Agent 的运行模式，决定整条流水线是否'经 LLM 增强'。"""
    if any(r.mode == AgentMode.LLM for r in results):
        return AgentMode.LLM
    if any(r.mode == AgentMode.FALLBACK for r in results):
        return AgentMode.FALLBACK
    return AgentMode.DETERMINISTIC
