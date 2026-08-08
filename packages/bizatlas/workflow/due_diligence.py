from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data import repo
from bizatlas.ingest.fixtures import load_fixture_company
from bizatlas.orchestrator.analyze import generate_onepager_report, run_analyze


# 需要强制人工复核的高风险等级（研判/出报告时打标，提交前必须 approve）
REVIEW_REQUIRED_GRADES = {"ORANGE", "RED", "BLACK"}
REVIEW_DECISIONS = {"approve", "reject", "return"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _template_path() -> Path:
    return get_settings().root / "content" / "workflows" / "due_diligence.yaml"


def load_template() -> dict[str, Any]:
    with _template_path().open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _checklist_status(company_id: str, manual_flags: dict[str, bool], template: dict[str, Any]) -> list[dict[str, Any]]:
    company = repo.get_company(company_id)
    metrics = repo.load_metrics(company_id) if company else []
    items = []
    for item in template.get("checklist") or []:
        source = item.get("source")
        done = False
        detail = ""
        if source == "metrics":
            done = len(metrics) > 0
            detail = f"{len(metrics)} 项指标" if done else "缺少财务指标"
        elif source == "company":
            done = bool(company and company.get("name"))
            detail = company.get("name") if done else "缺少企业名称"
        elif source == "events":
            # optional: mark done if manual or if fixture events were seeded into payload later
            done = bool(manual_flags.get(item["id"]))
            detail = "已勾选/已导入" if done else "可选"
        elif source == "manual":
            done = bool(manual_flags.get(item["id"]))
            detail = "已勾选" if done else "未勾选"
        items.append(
            {
                "id": item["id"],
                "label": item["label"],
                "required": bool(item.get("required")),
                "done": done,
                "detail": detail,
            }
        )
    return items


def _required_ready(checklist: list[dict[str, Any]]) -> bool:
    return all(i["done"] for i in checklist if i["required"])


def _snapshot(workflow_id: str) -> dict[str, Any]:
    row = repo.get_workflow(workflow_id)
    if not row:
        raise ValueError(f"workflow not found: {workflow_id}")
    template = load_template()
    payload = row.get("payload") or {}
    manual = payload.get("manual_flags") or {}
    checklist = _checklist_status(row["company_id"], manual, template)
    ready = _required_ready(checklist)
    stages = template.get("stages") or []
    stage_ids = [s["id"] for s in stages]
    current = row["stage"]
    idx = stage_ids.index(current) if current in stage_ids else 0

    return {
        "id": row["id"],
        "template_id": row["template_id"],
        "template_name": template.get("name"),
        "company_id": row["company_id"],
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
        "required_ready": ready,
        "analyze": payload.get("analyze"),
        "report": payload.get("report"),
        "blockers": payload.get("blockers") or [],
        "history": payload.get("history") or [],
        "review": payload.get("review"),
        "review_passed": payload.get("review_passed", False),
        "requires_review": payload.get("requires_review", False),
        "audit_trail": payload.get("audit_trail") or [],
        "remediation_tasks": payload.get("remediation_tasks") or [],
        "updated_at": row.get("updated_at"),
    }


def start_due_diligence(
    *,
    company_id: str | None = None,
    fixture_id: str | None = None,
    name: str | None = None,
    industry: str = "",
) -> dict[str, Any]:
    """Start workflow. Prefer fixture_id for demo; or existing/new company_id."""
    template = load_template()
    events: dict[str, Any] = {}

    if fixture_id:
        data = load_fixture_company(fixture_id)
        cid = data.get("id") or f"fixture-{fixture_id}"
        company = repo.ensure_company(
            cid,
            str(data.get("name") or name or fixture_id),
            str(data.get("industry") or industry or ""),
        )
        # seed metrics from fixture into DB so checklist/metrics path works
        metrics = data.get("_metrics") or []
        if metrics:
            repo.replace_metrics(company["id"], metrics)
        events = data.get("_events") or {}
        company_id = company["id"]
    else:
        if not company_id:
            company = repo.create_company(name or "贷前尽调企业", industry)
            company_id = company["id"]
        elif not repo.get_company(company_id):
            raise ValueError(f"company not found: {company_id}")

    payload: dict[str, Any] = {
        "manual_flags": {"risk_events": bool(events)} if events else {},
        "events": events,
        "fixture_id": fixture_id,
        "history": [{"action": "start", "stage": "checklist"}],
        "blockers": [],
    }
    checklist = _checklist_status(company_id, payload["manual_flags"], template)
    stage = "ready" if _required_ready(checklist) else "checklist"
    wid = repo.save_workflow("due_diligence", company_id, stage, payload)
    return _snapshot(wid)


def get_due_diligence(workflow_id: str) -> dict[str, Any]:
    return _snapshot(workflow_id)


def _build_remediation_tasks(risk: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从风险命中生成整改工单（对标 AuditPilot 的整改闭环）。

    每个命中规则 → 一张工单，含负责人角色 / 优先级 / 时限 / 验收口径。
    """
    if not risk:
        return []
    hits = risk.get("hits") or []
    tasks: list[dict[str, Any]] = []
    for i, hit in enumerate(hits, 1):
        severity = str(hit.get("severity") or "中")
        priority = {"高": "P0", "中": "P1", "低": "P2"}.get(severity, "P1")
        due_days = {"高": 7, "中": 14, "低": 30}.get(severity, 14)
        owner = {
            "财务": "财务复核岗",
            "经营": "经营分析岗",
            "行业": "行业研究岗",
            "舆情": "舆情监控岗",
            "关联": "合规岗",
        }.get(str(hit.get("dimension") or ""), "风控岗")
        tasks.append(
            {
                "task_id": f"REM-{i:02d}",
                "title": str(hit.get("name") or hit.get("message") or "风险整改"),
                "detail": str(hit.get("message") or ""),
                "dimension": str(hit.get("dimension") or ""),
                "severity": severity,
                "priority": priority,
                "owner": owner,
                "due_days": due_days,
                "success_metric": "该维度指标回到安全阈值内并提交复核",
                "status": "未开始",
            }
        )
    return tasks


def review_due_diligence(
    workflow_id: str,
    *,
    reviewer: str,
    decision: str,
    comment: str = "",
) -> dict[str, Any]:
    """人工复核状态机（对标 AuditPilot 的 add_review）。

    decision:
      - approve：通过复核，允许提交（设 review_passed）
      - reject ：驳回，阻断提交（终态，需重新走流程）
      - return ：退回修改，stage 回退到 analyzed 重新研判
    每次决策追加到 audit_trail（复核人 / 决策 / 意见 / 时间），驱动 lifecycle 流转。
    """
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"unknown decision: {decision}，应为 {sorted(REVIEW_DECISIONS)}")
    row = repo.get_workflow(workflow_id)
    if not row:
        raise ValueError(f"workflow not found: {workflow_id}")
    payload = row.get("payload") or {}
    payload.setdefault("history", [])
    payload.setdefault("audit_trail", [])
    payload.setdefault("manual_flags", {})

    entry = {
        "action": "review",
        "reviewer": reviewer,
        "decision": decision,
        "comment": comment,
        "at": _now_iso(),
    }
    payload["audit_trail"].append(entry)
    review_status = {
        "approve": "approved",
        "reject": "rejected",
        "return": "returned",
    }[decision]
    payload["review"] = {
        "status": review_status,
        "reviewer": reviewer,
        "decided_at": _now_iso(),
        "comment": comment,
    }

    stage = row["stage"]
    if decision == "approve":
        payload["review_passed"] = True
    elif decision == "return":
        payload["review_passed"] = False
        stage = "analyzed"  # 退回重新研判
    elif decision == "reject":
        payload["review_passed"] = False
        # 驳回：生成整改工单，提交被阻断
        payload["remediation_tasks"] = _build_remediation_tasks(
            (payload.get("analyze") or {}).get("risk")
        )

    payload["history"].append({"action": "review", "decision": decision, "reviewer": reviewer})
    repo.save_workflow(row["template_id"], row["company_id"], stage, payload, workflow_id=workflow_id)
    return _snapshot(workflow_id)


def advance_due_diligence(
    workflow_id: str,
    *,
    action: str,
    confirm: bool = False,
    manual_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    actions:
      - sync: refresh checklist / stage
      - mark: update manual checklist flags
      - analyze: run risk analyze
      - report: generate onepager draft
      - submit: human confirm submit (gate on ORANGE+)
    """
    row = repo.get_workflow(workflow_id)
    if not row:
        raise ValueError(f"workflow not found: {workflow_id}")
    template = load_template()
    payload = row.get("payload") or {}
    payload.setdefault("history", [])
    payload.setdefault("manual_flags", {})
    if manual_flags:
        payload["manual_flags"].update({k: bool(v) for k, v in manual_flags.items()})

    company_id = row["company_id"]
    stage = row["stage"]
    blockers: list[str] = []

    if action in {"sync", "mark"}:
        checklist = _checklist_status(company_id, payload["manual_flags"], template)
        stage = "ready" if _required_ready(checklist) else "checklist"
        if stage == "checklist":
            blockers = [i["label"] for i in checklist if i["required"] and not i["done"]]

    elif action == "analyze":
        checklist = _checklist_status(company_id, payload["manual_flags"], template)
        if not _required_ready(checklist):
            raise ValueError("必填资料未齐套，无法研判")
        # fixture_id keeps event veto path; otherwise use uploaded company metrics
        analyze_key = payload.get("fixture_id") or company_id
        analyzed = run_analyze(AnalyzeRequest(company_id=analyze_key, intent="analyze_risk"))
        payload["analyze"] = {
            "summary": analyzed.get("summary"),
            "rules_hit": analyzed.get("rules_hit"),
            "metrics_count": analyzed.get("metrics_count"),
            "risk": analyzed.get("risk"),
        }
        stage = "analyzed"
        payload["history"].append({"action": "analyze", "grade": analyzed["summary"]["grade"]})

    elif action == "report":
        if stage not in {"analyzed", "reported", "awaiting_human"} and not payload.get("analyze"):
            raise ValueError("请先完成风险研判")
        analyze_key = payload.get("fixture_id") or company_id
        report = generate_onepager_report(analyze_key, confirm_export=False)
        payload["report"] = {
            "report_id": report.get("report_id"),
            "status": report.get("status"),
            "summary": report.get("summary"),
            "markdown_preview": (report.get("markdown") or "")[:1200],
        }
        stage = "awaiting_human"
        grade = ((payload.get("analyze") or {}).get("summary") or {}).get("grade")
        if grade in REVIEW_REQUIRED_GRADES:
            payload["requires_review"] = True
            payload.setdefault("review_passed", False)
        payload["history"].append({"action": "report", "report_id": report.get("report_id")})

    elif action == "submit":
        if not confirm:
            raise ValueError("提交需要 confirm=true（人在回路）")
        if not payload.get("report"):
            raise ValueError("请先生成报告草稿")
        # 高风险结论：提交前必须通过人工复核（人在回路硬门禁）
        if payload.get("requires_review") and not payload.get("review_passed"):
            raise ValueError("高风险结论需先通过人工复核（review_due_diligence approve）")
        grade = ((payload.get("analyze") or {}).get("summary") or {}).get("grade")
        gate = set(template.get("gate_grade_for_submit") or [])
        # always require confirm; gate grades just annotate
        if grade in gate:
            payload["gate_note"] = f"等级 {grade}：已人工确认后提交"
        # export on submit
        analyze_key = payload.get("fixture_id") or company_id
        exported = generate_onepager_report(analyze_key, confirm_export=True)
        payload["report"]["export_path"] = exported.get("export_path")
        payload["report"]["status"] = "exported"
        stage = "submitted"
        payload["history"].append({"action": "submit", "confirm": True, "grade": grade})

    else:
        raise ValueError(f"unknown action: {action}")

    payload["blockers"] = blockers
    repo.save_workflow(
        row["template_id"],
        company_id,
        stage,
        payload,
        workflow_id=workflow_id,
    )
    return _snapshot(workflow_id)
