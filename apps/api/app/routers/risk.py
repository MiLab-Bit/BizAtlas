from __future__ import annotations

from bizatlas.compliance.statement import load_compliance_statement
from bizatlas.contracts.models import AnalyzeRequest, Envelope
from bizatlas.credit.decision import build_credit_decision
from bizatlas.observability import observe
from bizatlas.orchestrator.analyze import run_analyze
from bizatlas.validation.report import load_backtest_report
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.app.main import (
    settings,
)


class CreditDecisionRequest(BaseModel):
    """贷前授信准入决策请求。"""

    company_id: str
    applied_amount: float | None = Field(
        default=None, description="申请额度（万元）。缺省时仅返回额度系数区间，不给绝对金额"
    )
    tenor_months: int | None = Field(default=None, description="申请期限（月）")
    product: str = Field(default="流动资金贷款", description="授信产品名")
    include_stress: bool = Field(default=False, description="是否附带压力测试（贷前默认关，控延迟）")
    skip_polish: bool = Field(
        default=True,
        description="跳过 LLM 润色。决策数字本就不经 LLM，默认开启快路径",
    )


router = APIRouter()

@router.post("/v1/credit/decision")
@observe("api.credit_decision")
def credit_decision(req: CreditDecisionRequest) -> Envelope[dict]:
    """贷前授信准入决策。

    把通用风险研判收敛为贷前审批场景下的一个具体决策动作：
    是否准入、以什么条件准入、建议额度区间、是否必须转人工终审。

    决策档位与额度系数全部由确定性规则计算，不经过大模型；
    ORANGE 及以上评级、命中一票否决、担保链含失信主体、核心数据不足
    ——以上任一情形均强制转人工终审。
    """

    analyze_req = AnalyzeRequest(
        company_id=req.company_id,
        intent="analyze_risk",
        options={
            "include_stress": req.include_stress,
            "include_kg": True,
            "skip_polish": req.skip_polish,
            "fast": req.skip_polish,
        },
    )
    try:
        result = run_analyze(analyze_req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    decision = build_credit_decision(
        result,
        applied_amount=req.applied_amount,
        tenor_months=req.tenor_months,
        product=req.product,
    )
    return Envelope(
        ok=True,
        data={"decision": decision, "analysis": result},
        meta={
            "scenario": "pre_lending_credit_admission",
            "manual_gate_required": decision["manual_gate"]["required"],
            "llm_used_for_numbers": False,
            "fast_path": bool(req.skip_polish),
            "mode": settings.bizatlas_mode,
        },
    )

@router.get("/v1/validation/backtest")
def validation_backtest() -> Envelope[dict]:
    """风险评分有效性回溯验证报告。

    报告未生成时返回 available=false 并说明原因，不返回任何占位数字。
    """

    data = load_backtest_report()
    return Envelope(
        ok=True,
        data=data,
        meta={"available": bool(data.get("available"))},
    )

@router.get("/v1/compliance/statement")
def compliance_statement() -> Envelope[dict]:
    """数据授权与合规机制声明（含运行时数据源对账）。"""

    data = load_compliance_statement()
    rec = data.get("reconciliation") or {}
    return Envelope(
        ok=True,
        data=data,
        meta={
            "available": bool(data.get("available")),
            "source_count": data.get("source_count", 0),
            "declaration_consistent": rec.get("consistent"),
        },
    )

