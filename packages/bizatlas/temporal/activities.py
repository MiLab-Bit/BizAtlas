"""Activity 封装层：把 BizAtlas 领域函数包成 Temporal Activity。

设计原则：
- Workflow 只做确定性编排（顺序 / 分支 / 等待信号 / 维护本地状态），所有"会变的"
  操作（LLM 调用、RAG 检索、SQLite 读写、报告导出）一律落到 Activity，由 Temporal
  负责重试 / 超时 / 心跳 / 重放。
- Activity 内延迟 import 领域模块，避免 Worker 启动时一次性加载全部依赖。
- 跨边界数据统一用 dict / dataclass（见 common.py），不使用 pydantic 模型直传。
"""

from __future__ import annotations

from typing import Any

from temporalio import activity


# ======================================================================
# 多 Agent 研判管线
# ======================================================================

@activity.defn(name="run_analyze")
async def run_analyze_activity(inp: dict[str, Any]) -> dict[str, Any]:
    """评分内核（唯一事实源）：规则 + 计算 + 可选 LLM 润色。"""
    from bizatlas.contracts.models import AnalyzeRequest
    from bizatlas.orchestrator.analyze import run_analyze

    activity.heartbeat("scoring:start")
    req = AnalyzeRequest(**inp)
    result = run_analyze(req)
    activity.heartbeat("scoring:done")
    return result


@activity.defn(name="classify_company")
async def classify_activity(core: dict[str, Any]) -> dict[str, Any]:
    """分类 Agent：赛道/行业归类（无 LLM 时确定性降级）。"""
    from bizatlas.agents.classifier import classify_company

    res = classify_company(core.get("company") or {}, core.get("metrics") or [])
    return res.model_dump(mode="json")


@activity.defn(name="plan_research")
async def plan_activity(ctx: dict[str, Any]) -> dict[str, Any]:
    """规划 Agent：基于风险 + 企业 + 分类产出研究计划（失败感知）。"""
    from bizatlas.agents.planner import plan_research

    res = plan_research(ctx["risk"], ctx["company"], ctx.get("classification") or {})
    return res.model_dump(mode="json")


@activity.defn(name="research")
async def research_activity(ctx: dict[str, Any]) -> dict[str, Any]:
    """研究 Agent：本地 RAG 检索，填充研究计划各维度。"""
    from bizatlas.agents.researcher import research

    res = research(
        ctx.get("research_plan") or [],
        company_id=ctx.get("company_id"),
        fixture_id=ctx.get("fixture_id"),
    )
    return res.model_dump(mode="json")


@activity.defn(name="write_report")
async def write_activity(ctx: dict[str, Any]) -> dict[str, Any]:
    """写作 Agent：writer-only 叙事 + 披露（不改分，不改决策）。"""
    from bizatlas.agents.writer import write_report

    res = write_report(
        ctx["risk"],
        ctx.get("classification") or {},
        ctx.get("planner") or {},
        ctx.get("researcher") or {},
        ctx.get("company") or {},
    )
    return res.model_dump(mode="json")


# ======================================================================
# 贷前尽调状态机
# ======================================================================

@activity.defn(name="dd_create")
async def start_dd_activity(inp: dict[str, Any]) -> dict[str, Any]:
    """启动贷前尽调：建/取企业、灌 fixture 指标，返回原始 payload（不快照）。"""
    from bizatlas.workflow.due_diligence import create_due_diligence

    return create_due_diligence(
        company_id=inp.get("company_id"),
        fixture_id=inp.get("fixture_id"),
        name=inp.get("name"),
        industry=inp.get("industry") or "",
    )


@activity.defn(name="dd_compute_checklist")
async def compute_checklist_activity(args: dict[str, Any]) -> list[dict[str, Any]]:
    """计算 checklist 就绪状态（读 SQLite 指标数 / 企业名）。"""
    from bizatlas.workflow.due_diligence import _checklist_status, load_template

    template = load_template()
    company_id: str = args["company_id"]
    manual_flags: dict[str, bool] = args.get("manual_flags") or {}
    return _checklist_status(company_id, manual_flags, template)


@activity.defn(name="dd_export_onepager")
async def export_onepager_activity(analyze_key: str) -> dict[str, Any]:
    """submit 阶段：导出 one-pager 报告（Markdown/Word/PDF + 防篡改签名）。"""
    from bizatlas.orchestrator.analyze import generate_onepager_report

    return generate_onepager_report(analyze_key, confirm_export=True)


@activity.defn(name="dd_generate_report")
async def generate_report_activity(args: dict[str, Any]) -> dict[str, Any]:
    """report/submit 阶段：生成 one-pager 报告。

    confirm_export=True 才落盘导出（Markdown/Word/PDF + 防篡改签名）；
    report 草稿阶段传 False，submit 阶段传 True（人在回路硬门禁）。
    """
    from bizatlas.orchestrator.analyze import generate_onepager_report

    return generate_onepager_report(args["analyze_key"], confirm_export=bool(args.get("confirm_export")))


@activity.defn(name="dd_mirror")
async def mirror_dd_activity(args: dict[str, Any]) -> None:
    """每次状态变更后把镜像写入 SQLite，供 GET /v1/workflows 列表查询。

    Temporal 是事件溯源日志，不适合做"列表所有进行中工作流"这种扫描查询；
    SQLite 镜像保留轻量快照，列表明细走镜像，单一实例详情走 Temporal Query。
    """
    from bizatlas.data import repo

    repo.save_workflow(
        args["template_id"],
        args["company_id"],
        args["stage"],
        args["payload"],
        workflow_id=args["workflow_id"],
    )


@activity.defn(name="dd_load_template")
async def load_template_activity() -> dict[str, Any]:
    """读取贷前尽调模板 YAML（Workflow 启动时拉一次，避免 Workflow 内读盘）。"""
    from bizatlas.workflow.due_diligence import load_template

    return load_template()


__all__ = [
    "run_analyze_activity",
    "classify_activity",
    "plan_activity",
    "research_activity",
    "write_activity",
    "start_dd_activity",
    "compute_checklist_activity",
    "export_onepager_activity",
    "generate_report_activity",
    "mirror_dd_activity",
    "load_template_activity",
]
