"""工具调用的统一信封。

复用在 agents/base.py 中定义的 Disclosure（失败感知单元），保证治理层产出与
多 Agent 编排的披露语义一致：工具被拒/超时/出错时，必须显式说清楚，绝不静默。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from bizatlas.agents.base import Disclosure


class ToolResult(BaseModel):
    """治理后工具调用的统一返回信封。"""

    ok: bool = True
    output: Any = None
    disclosures: list[Disclosure] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def denied(cls, message: str) -> "ToolResult":
        return cls(
            ok=False,
            disclosures=[Disclosure(code="permission_denied", severity="warn", message=message)],
        )

    @classmethod
    def failed(cls, code: str, message: str) -> "ToolResult":
        return cls(
            ok=False,
            disclosures=[Disclosure(code=code, severity="warn", message=message)],
        )
