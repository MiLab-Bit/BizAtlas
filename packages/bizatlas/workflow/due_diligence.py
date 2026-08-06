from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.contracts.models import AnalyzeRequest
from bizatlas.data import repo
from bizatlas.ingest.fixtures import load_fixture_company
from bizatlas.orchestrator.analyze import generate_onepager_report, run_analyze


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
        payload["history"].append({"action": "report", "report_id": report.get("report_id")})

    elif action == "submit":
        if not confirm:
            raise ValueError("提交需要 confirm=true（人在回路）")
        if not payload.get("report"):
            raise ValueError("请先生成报告草稿")
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
