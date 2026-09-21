"""DueDiligenceWorkflow —— 贷前尽调状态机（Temporal 底座）。

替换原来的手写 SQLite 状态机（workflow/due_diligence.py 的 advance/review）。
Temporal 带来的收益：
- 状态即事件溯源：Workflow 实例本身持有 stage/payload，每次 advance/review 是 Update，
  审计轨迹 = Temporal 事件历史（天然不可篡改、可回放）。
- 人在回路：review(approve/reject/return) 与 submit(confirm) 是显式 Update 门禁，
  高风险结论不通过 review 无法 submit。
- 持久化/可恢复：进程崩溃后 Workflow 从事件历史恢复，不丢状态、不重复导出。
- 可观测：Temporal Web UI 直接看到每个贷前尽调实例的当前 stage 与历史 Update。

边界划分：
- 纯状态逻辑（stage 流转、review 状态机、checklist 就绪判定、整改工单生成）在 Workflow 内，
  保证确定性、可测试。
- IO（建企业、读指标数、跑评分、生成/导出报告、写 SQLite 镜像）走 Activity。
- Query get_snapshot 只读内存状态，绝不调 Activity（Query 不允许执行 Activity）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from bizatlas.temporal.activities import (
    compute_checklist_activity,
    generate_report_activity,
    load_template_activity,
    mirror_dd_activity,
    run_analyze_activity,
    start_dd_activity,
)
from bizatlas.temporal.common import DueDiligenceInput

# 从 legacy 模块复用纯函数（无 IO、确定性），避免重复实现
from bizatlas.workflow.due_diligence import (
    REVIEW_DECISIONS,
    REVIEW_REQUIRED_GRADES,
    _build_remediation_tasks,
    _required_ready,
)

_ACT_TIMEOUT = timedelta(seconds=300)
_ACT_RETRY = RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ValueError"])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@workflow.defn(name="DueDiligenceWorkflow")
class DueDiligenceWorkflow:
    def __init__(self) -> None:
        self.wid: str | None = None
        self.template_id: str = "due_diligence"
        self.company_id: str | None = None
        self.stage: str = "checklist"
        self.payload: dict[str, Any] = {}
        self.template: dict[str, Any] = {}

    @workflow.run
    async def run(self, inp: DueDiligenceInput) -> dict[str, Any]:
        # 模板只在启动时读一次（避免 Workflow 内反复读盘）
        self.template = await workflow.execute_activity(
            load_template_activity, start_to_close_timeout=timedelta(seconds=30)
        )
        created = await workflow.execute_activity(
            start_dd_activity, inp.__dict__, start_to_close_timeout=timedelta(seconds=60)
        )
        self.wid = created["workflow_id"]
        self.company_id = created["company_id"]
        self.stage = created["stage"]
        self.payload = created["payload"]
        await self._refresh_checklist()
        await self._mirror()

        # 人在回路：等待直到 submit（终态）。reject/return 维持 open 仍可继续 Update。
        await workflow.wait_condition(lambda: self.stage == "submitted")
        return self._snapshot()

    # ==================================================================
    # Update：advance / review（可返回值，API 网关用 execute_update 同步拿快照）
    # ==================================================================
    @workflow.update
    async def advance(self, action: str, confirm: bool = False, manual_flags: dict[str, bool] | None = None) -> dict[str, Any]:
        # 客户端可能在 run() 初始化完成前就发来 Update：先等状态就绪，
        # 否则 company_id 仍为 None，checklist 会误判为"未齐套"。
        await workflow.wait_condition(lambda: self.wid is not None)
        if action in ("sync", "mark"):
            if manual_flags:
                self.payload.setdefault("manual_flags", {}).update(
                    {k: bool(v) for k, v in manual_flags.items()}
                )
            await self._refresh_checklist()
            self.stage = "ready" if self.payload["required_ready"] else "checklist"
            if self.stage == "checklist":
                self.payload["blockers"] = [
                    i["label"] for i in self.payload["checklist"] if i["required"] and not i["done"]
                ]
        elif action == "analyze":
            await self._refresh_checklist()
            if not self.payload["required_ready"]:
                raise ValueError("必填资料未齐套，无法研判")
            analyze_key = self.payload.get("fixture_id") or self.company_id
            analyzed = await workflow.execute_activity(
                run_analyze_activity,
                {
                    "company_id": analyze_key,
                    "intent": "analyze_risk",
                    "options": {"include_stress": True, "include_kg": True},
                },
                start_to_close_timeout=_ACT_TIMEOUT,
                retry_policy=_ACT_RETRY,
            )
            self.payload["analyze"] = {
                "summary": analyzed.get("summary"),
                "rules_hit": analyzed.get("rules_hit"),
                "metrics_count": analyzed.get("metrics_count"),
                "risk": analyzed.get("risk"),
            }
            self.stage = "analyzed"
            self.payload.setdefault("history", []).append(
                {"action": "analyze", "grade": analyzed["summary"]["grade"]}
            )
        elif action == "report":
            if self.stage not in ("analyzed", "reported", "awaiting_human") and not self.payload.get("analyze"):
                raise ValueError("请先完成风险研判")
            analyze_key = self.payload.get("fixture_id") or self.company_id
            report = await workflow.execute_activity(
                generate_report_activity,
                {"analyze_key": analyze_key, "confirm_export": False},
                start_to_close_timeout=_ACT_TIMEOUT,
                retry_policy=_ACT_RETRY,
            )
            self.payload["report"] = {
                "report_id": report.get("report_id"),
                "status": report.get("status"),
                "summary": report.get("summary"),
                "markdown_preview": (report.get("markdown") or "")[:1200],
            }
            self.stage = "awaiting_human"
            grade = (self.payload.get("analyze") or {}).get("summary", {}).get("grade")
            if grade in REVIEW_REQUIRED_GRADES:
                self.payload["requires_review"] = True
                self.payload.setdefault("review_passed", False)
            self.payload.setdefault("history", []).append(
                {"action": "report", "report_id": report.get("report_id")}
            )
        elif action == "submit":
            if not confirm:
                raise ValueError("提交需要 confirm=true（人在回路）")
            if not self.payload.get("report"):
                raise ValueError("请先生成报告草稿")
            if self.payload.get("requires_review") and not self.payload.get("review_passed"):
                raise ValueError("高风险结论需先通过人工复核（review approve）")
            grade = (self.payload.get("analyze") or {}).get("summary", {}).get("grade")
            gate = set(self.template.get("gate_grade_for_submit") or [])
            if grade in gate:
                self.payload["gate_note"] = f"等级 {grade}：已人工确认后提交"
            analyze_key = self.payload.get("fixture_id") or self.company_id
            exported = await workflow.execute_activity(
                generate_report_activity,
                {"analyze_key": analyze_key, "confirm_export": True},
                start_to_close_timeout=_ACT_TIMEOUT,
                retry_policy=_ACT_RETRY,
            )
            self.payload["report"]["export_path"] = exported.get("export_path")
            self.payload["report"]["status"] = "exported"
            self.stage = "submitted"
            self.payload.setdefault("history", []).append(
                {"action": "submit", "confirm": True, "grade": grade}
            )
        else:
            raise ValueError(f"unknown action: {action}")

        await self._mirror()
        return self._snapshot()

    @workflow.update
    async def review(self, decision: str, comment: str = "", reviewer: str = "") -> dict[str, Any]:
        await workflow.wait_condition(lambda: self.wid is not None)
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"unknown decision: {decision}，应为 {sorted(REVIEW_DECISIONS)}")
        self.payload.setdefault("history", [])
        self.payload.setdefault("audit_trail", [])
        self.payload.setdefault("manual_flags", {})

        entry = {
            "action": "review",
            "reviewer": reviewer,
            "decision": decision,
            "comment": comment,
            "at": _now_iso(),
        }
        self.payload["audit_trail"].append(entry)
        review_status = {"approve": "approved", "reject": "rejected", "return": "returned"}[decision]
        self.payload["review"] = {
            "status": review_status,
            "reviewer": reviewer,
            "decided_at": _now_iso(),
            "comment": comment,
        }

        if decision == "approve":
            self.payload["review_passed"] = True
        elif decision == "return":
            self.payload["review_passed"] = False
            self.stage = "analyzed"  # 退回重新研判
        elif decision == "reject":
            self.payload["review_passed"] = False
            self.payload["remediation_tasks"] = _build_remediation_tasks(
                (self.payload.get("analyze") or {}).get("risk")
            )

        self.payload.setdefault("history", []).append(
            {"action": "review", "decision": decision, "reviewer": reviewer}
        )
        await self._mirror()
        return self._snapshot()

    # ==================================================================
    # Query：只读内存状态
    # ==================================================================
    @workflow.query
    def get_snapshot(self) -> dict[str, Any]:
        return self._snapshot()

    # ==================================================================
    # 内部辅助
    # ==================================================================
    async def _refresh_checklist(self) -> None:
        checklist = await workflow.execute_activity(
            compute_checklist_activity,
            {
                "company_id": self.company_id,
                "manual_flags": self.payload.get("manual_flags") or {},
            },
            start_to_close_timeout=timedelta(seconds=60),
        )
        self.payload["checklist"] = checklist
        self.payload["required_ready"] = _required_ready(checklist)

    async def _mirror(self) -> None:
        await workflow.execute_activity(
            mirror_dd_activity,
            {
                "workflow_id": self.wid,
                "template_id": self.template_id,
                "company_id": self.company_id,
                "stage": self.stage,
                "payload": self.payload,
            },
            start_to_close_timeout=timedelta(seconds=30),
        )

    def _snapshot(self) -> dict[str, Any]:
        template = self.template
        payload = self.payload
        checklist = payload.get("checklist") or []
        stages = template.get("stages") or []
        stage_ids = [s["id"] for s in stages]
        current = self.stage
        idx = stage_ids.index(current) if current in stage_ids else 0
        return {
            "id": self.wid,
            "template_id": self.template_id,
            "template_name": template.get("name"),
            "company_id": self.company_id,
            "stage": current,
            "stages": [
                {
                    **s,
                    "state": (
                        "done"
                        if stage_ids.index(s["id"]) < idx
                        else ("current" if s["id"] == current else "pending")
                    ),
                }
                for s in stages
            ],
            "checklist": checklist,
            "required_ready": _required_ready(checklist),
            "analyze": payload.get("analyze"),
            "report": payload.get("report"),
            "blockers": payload.get("blockers") or [],
            "history": payload.get("history") or [],
            "review": payload.get("review"),
            "review_passed": payload.get("review_passed", False),
            "requires_review": payload.get("requires_review", False),
            "audit_trail": payload.get("audit_trail") or [],
            "remediation_tasks": payload.get("remediation_tasks") or [],
            "updated_at": _now_iso(),
        }
