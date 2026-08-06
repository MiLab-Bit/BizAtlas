from __future__ import annotations

from typing import Any

from bizatlas.contracts.models import AnalyzeRequest, MetricValue, RiskResult
from bizatlas.data import repo
from bizatlas.industry.benchmarks import compare_to_industry
from bizatlas.ingest.fixtures import load_fixture_company
from bizatlas.kg.graph import build_guarantee_graph
from bizatlas.report.credit import build_credit_assessment
from bizatlas.report.docx_export import export_credit_docx, export_onepager_docx
from bizatlas.report.onepager import build_onepager, render_onepager_markdown
from bizatlas.report.pdf_export import export_report_pdf
from bizatlas.report.titles import status_label
from bizatlas.risk.attribution import build_attribution
from bizatlas.risk.conflicts import detect_conflicts
from bizatlas.risk.score import score_risk
from bizatlas.risk.stress import run_stress
from bizatlas.rules.engine import RuleEngine


def _resolve_inputs(
    company_id: str,
) -> tuple[str, list[MetricValue], list[MetricValue], dict[str, Any], dict[str, Any], str | None]:
    events: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    fixture_id = None
    alt: list[MetricValue] = []
    if company_id.startswith("fixture:"):
        fixture_id = company_id.split(":", 1)[1]
    elif company_id in {"healthy", "risky", "defaulted"}:
        fixture_id = company_id

    if fixture_id:
        data = load_fixture_company(fixture_id)
        metrics = data.get("_metrics") or []
        alt = data.get("_alt_metrics") or []
        events = data.get("_events") or {}
        cid = data.get("id") or company_id
        meta = {
            "id": cid,
            "name": data.get("name"),
            "industry": data.get("industry"),
            "fixture_id": fixture_id,
            "demo_note": data.get("demo_note"),
        }
        return cid, metrics, alt, events, meta, fixture_id

    company = repo.get_company(company_id)
    if not company:
        raise ValueError(f"company not found: {company_id}")
    metrics = repo.load_metrics(company_id)
    meta = {
        "id": company["id"],
        "name": company["name"],
        "industry": company.get("industry") or "",
    }
    return company_id, metrics, alt, events, meta, None


def run_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    company_id, metrics, alt_metrics, events, meta, fixture_id = _resolve_inputs(req.company_id)
    opts = req.options or {}
    include_stress = bool(opts.get("include_stress", True))
    include_kg = bool(opts.get("include_kg", True))

    observations = list(metrics) + list(alt_metrics)
    conflicts = detect_conflicts(observations)

    engine = RuleEngine()
    hits = engine.match(metrics, events=events)
    risk: RiskResult = score_risk(
        company_id,
        metrics,
        hits,
        events=events,
        conflicts=len(conflicts),
    )
    risk_dump = risk.model_dump(mode="json")
    metrics_dump = [m.model_dump(mode="json") for m in metrics]

    # 结论句：LLM 润色 + Number Gate（失败回退模板句）
    headline = risk.headline
    headline_meta = {"polished": False, "llm_used": False, "gate_ok": True}
    try:
        from bizatlas.llm.polish import polish_headline

        polished_h = polish_headline(headline, metrics=metrics_dump, risk=risk_dump)
        headline = polished_h["text"]
        headline_meta = {
            "polished": polished_h["polished"],
            "llm_used": polished_h["llm_used"],
            "gate_ok": polished_h["gate_ok"],
        }
        risk_dump["headline"] = headline
    except Exception:  # noqa: BLE001
        pass

    if repo.get_company(company_id):
        repo.save_risk_score(company_id, risk_dump)

    graph = build_guarantee_graph(company_id, fixture_id=fixture_id) if include_kg else None
    attribution = build_attribution(risk.dimensions, hits, metrics)

    # 五维归因人话解说：仅高分维度（控延迟），只翻译不另算分
    try:
        from bizatlas.llm.polish import explain_attribution_dim

        ranked = sorted(attribution, key=lambda d: float(d.get("score") or 0), reverse=True)
        explain_ids = {d.get("id") for d in ranked[:2]}
        for dim in attribution:
            if dim.get("id") in explain_ids:
                dim["narrative"] = explain_attribution_dim(
                    dim, metrics=metrics_dump, risk=risk_dump
                )
            else:
                dim.setdefault("narrative", "")
    except Exception:  # noqa: BLE001
        for dim in attribution:
            dim.setdefault("narrative", "")

    industry = compare_to_industry(meta.get("industry"), metrics)
    stress = run_stress(company_id, metrics, events, baseline=risk) if include_stress else None

    onepager = build_onepager(
        company=meta,
        risk=risk_dump,
        metrics_count=len(metrics),
    )

    return {
        "task_id": f"local-{company_id}",
        "status": "succeeded",
        "summary": {
            "headline": headline,
            "grade": risk.grade.value,
            "score": risk.score,
            "headline_meta": headline_meta,
        },
        "risk": risk_dump,
        "company": meta,
        "metrics": metrics_dump,
        "metrics_count": len(metrics),
        "rules_hit": len(hits),
        "report_id": None,
        "onepager": onepager,
        "graph": graph,
        "attribution": attribution,
        "conflicts": conflicts,
        "industry_benchmark": industry,
        "stress": stress,
        "citations": [
            {
                "id": m.source.ref if m.source else m.name,
                "label": m.name,
                "page": m.source.page if m.source else None,
                "tier": m.tier.value,
                "value": m.value,
            }
            for m in observations
        ],
    }


def generate_onepager_report(company_id: str, *, confirm_export: bool = False) -> dict[str, Any]:
    result = run_analyze(
        AnalyzeRequest(
            company_id=company_id,
            intent="analyze_risk",
            template_id="risk_onepager",
            options={"include_stress": False},
        )
    )
    payload = result.get("onepager") or {}
    try:
        from bizatlas.llm.polish import polish_onepager_lede

        payload = polish_onepager_lede(
            payload,
            metrics=result.get("metrics") or [],
            risk=result.get("risk") or {},
        )
    except Exception:  # noqa: BLE001
        pass
    cid = (result.get("company") or {}).get("id") or company_id
    status = "exported" if confirm_export else "generated"
    report_id = repo.save_report(cid, "risk_onepager", payload, status=status)
    markdown = render_onepager_markdown(payload)

    export_path = None
    docx_path = None
    pdf_path = None
    if confirm_export:
        out_md = repo.export_dir() / f"{report_id}_onepager.md"
        out_md.write_text(markdown, encoding="utf-8")
        export_path = str(out_md)
        out_docx = repo.export_dir() / f"{report_id}_onepager.docx"
        export_onepager_docx(payload, out_docx)
        docx_path = str(out_docx)
        out_pdf = repo.export_dir() / f"{report_id}_onepager.pdf"
        export_report_pdf(payload, out_pdf, kind="onepager")
        pdf_path = str(out_pdf)

    return {
        "report_id": report_id,
        "status": status,
        "status_label": status_label(status, exported=confirm_export),
        "analysis_title": payload.get("analysis_title"),
        "onepager": payload,
        "markdown": markdown,
        "export_path": export_path,
        "docx_path": docx_path,
        "pdf_path": pdf_path,
        "summary": result.get("summary"),
        "company": result.get("company"),
    }


def generate_credit_report(company_id: str, *, confirm_export: bool = False) -> dict[str, Any]:
    result = run_analyze(
        AnalyzeRequest(
            company_id=company_id,
            intent="analyze_risk",
            template_id="credit_assessment",
            options={"include_stress": False},
        )
    )
    metrics = result.get("metrics") or []
    risk = result.get("risk") or {}
    payload = build_credit_assessment(
        company=result.get("company") or {},
        risk=risk,
        metrics=metrics,
    )
    try:
        from bizatlas.llm.polish import polish_report_sections

        payload["sections"] = polish_report_sections(
            payload.get("sections") or [],
            metrics=metrics,
            risk=risk,
        )
    except Exception:  # noqa: BLE001
        pass
    cid = (result.get("company") or {}).get("id") or company_id
    status = "exported" if confirm_export else "generated"
    report_id = repo.save_report(cid, "credit_assessment", payload, status=status)
    export_path = None
    pdf_path = None
    if confirm_export:
        out = repo.export_dir() / f"{report_id}_credit.docx"
        export_credit_docx(payload, out)
        export_path = str(out)
        out_pdf = repo.export_dir() / f"{report_id}_credit.pdf"
        export_report_pdf(payload, out_pdf, kind="credit")
        pdf_path = str(out_pdf)
    return {
        "report_id": report_id,
        "status": status,
        "status_label": status_label(status, exported=confirm_export),
        "analysis_title": payload.get("analysis_title"),
        "credit": payload,
        "docx_path": export_path,
        "pdf_path": pdf_path,
        "summary": result.get("summary"),
        "company": result.get("company"),
    }
