from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
from bizatlas.contracts.integrity import sign


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


def _want_skip_polish(opts: dict[str, Any]) -> bool:
    """贷前快路径 / demo：跳过 LLM 润色，数字与决策本就不依赖 LLM。"""
    if opts.get("skip_polish") is True or opts.get("fast") is True:
        return True
    # 显式 false 才强制润色；缺省保持历史行为（会润色）
    return False


def _apply_llm_polish(
    *,
    headline: str,
    risk_dump: dict[str, Any],
    metrics_dump: list[dict[str, Any]],
    attribution: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """并行润色结论句 + 最高分两维归因；任一步失败回退模板，控延迟。"""
    from bizatlas.llm.polish import explain_attribution_dim, polish_headline

    headline_meta = {"polished": False, "llm_used": False, "gate_ok": True}
    ranked = sorted(attribution, key=lambda d: float(d.get("score") or 0), reverse=True)
    explain_targets = [d for d in ranked[:2] if d.get("id")]

    def _headline_job() -> dict[str, Any]:
        return polish_headline(headline, metrics=metrics_dump, risk=risk_dump)

    def _dim_job(dim: dict[str, Any]) -> tuple[str, str]:
        return str(dim.get("id")), explain_attribution_dim(
            dim, metrics=metrics_dump, risk=risk_dump
        )

    narratives: dict[str, str] = {}
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_headline_job): "headline"}
            for dim in explain_targets:
                futures[pool.submit(_dim_job, dim)] = f"dim:{dim.get('id')}"
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    result = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if key == "headline" and isinstance(result, dict):
                    headline = result.get("text") or headline
                    headline_meta = {
                        "polished": bool(result.get("polished")),
                        "llm_used": bool(result.get("llm_used")),
                        "gate_ok": bool(result.get("gate_ok", True)),
                    }
                    risk_dump["headline"] = headline
                elif key.startswith("dim:") and isinstance(result, tuple):
                    dim_id, text = result
                    narratives[dim_id] = text or ""
    except Exception:  # noqa: BLE001
        pass

    for dim in attribution:
        dim_id = dim.get("id")
        if dim_id in narratives:
            dim["narrative"] = narratives[dim_id]
        else:
            dim.setdefault("narrative", "")
    return headline, headline_meta, attribution


def run_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    company_id, metrics, alt_metrics, events, meta, fixture_id = _resolve_inputs(req.company_id)
    opts = req.options or {}
    include_stress = bool(opts.get("include_stress", True))
    include_kg = bool(opts.get("include_kg", True))
    skip_polish = _want_skip_polish(opts)

    observations = list(metrics) + list(alt_metrics)
    conflicts = detect_conflicts(observations)

    engine = RuleEngine()
    hits = engine.match(metrics, events=events, canary_key=company_id)
    risk: RiskResult = score_risk(
        company_id,
        metrics,
        hits,
        events=events,
        conflicts=len(conflicts),
    )
    risk_dump = risk.model_dump(mode="json")
    metrics_dump = [m.model_dump(mode="json") for m in metrics]

    headline = risk.headline
    headline_meta = {"polished": False, "llm_used": False, "gate_ok": True, "skipped": skip_polish}

    try:
        if repo.get_company(company_id):
            repo.save_risk_score(company_id, risk_dump)
    except Exception:  # noqa: BLE001 — fixture / 空库场景不阻断研判
        pass

    graph = build_guarantee_graph(company_id, fixture_id=fixture_id) if include_kg else None
    attribution = build_attribution(risk.dimensions, hits, metrics)

    if not skip_polish:
        try:
            headline, headline_meta, attribution = _apply_llm_polish(
                headline=headline,
                risk_dump=risk_dump,
                metrics_dump=metrics_dump,
                attribution=attribution,
            )
            headline_meta["skipped"] = False
        except Exception:  # noqa: BLE001
            for dim in attribution:
                dim.setdefault("narrative", "")
    else:
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
        "fast_path": skip_polish,
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


def generate_onepager_report(
    company_id: str,
    *,
    confirm_export: bool = False,
    use_pipeline: bool = False,
) -> dict[str, Any]:
    from bizatlas.agents.pipeline import run_analysis_pipeline

    opts: dict[str, Any] = {"include_stress": False}
    if use_pipeline:
        opts["use_pipeline"] = True
    result = (
        run_analysis_pipeline(
            AnalyzeRequest(
                company_id=company_id,
                intent="analyze_risk",
                template_id="risk_onepager",
                options=opts,
            )
        )
        if use_pipeline
        else run_analyze(
            AnalyzeRequest(
                company_id=company_id,
                intent="analyze_risk",
                template_id="risk_onepager",
                options=opts,
            )
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
    # 多 Agent 流水线产出（writer-only 叙事 + 失败感知披露）注入报告
    if use_pipeline:
        payload["narrative"] = result.get("narrative") or {}
        payload["disclosures"] = result.get("disclosures") or []
        payload["pipeline_mode"] = result.get("pipeline_mode")
    cid = (result.get("company") or {}).get("id") or company_id
    status = "exported" if confirm_export else "generated"
    report_id = repo.save_report(cid, "risk_onepager", payload, status=status)
    markdown = render_onepager_markdown(payload)

    export_path = None
    docx_path = None
    pdf_path = None
    integrity = None
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
        # 报告防篡改：对导出载荷签名，落盘 .integrity.json，供独立复核
        rec = sign(report_id, payload)
        (repo.export_dir() / f"{report_id}_onepager.integrity.json").write_text(
            rec.model_dump_json(), encoding="utf-8"
        )
        integrity = rec.model_dump()

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
        "integrity": integrity,
        "summary": result.get("summary"),
        "company": result.get("company"),
    }


def generate_credit_report(
    company_id: str,
    *,
    confirm_export: bool = False,
    use_pipeline: bool = False,
) -> dict[str, Any]:
    from bizatlas.agents.pipeline import run_analysis_pipeline

    opts: dict[str, Any] = {"include_stress": False}
    if use_pipeline:
        opts["use_pipeline"] = True
    result = (
        run_analysis_pipeline(
            AnalyzeRequest(
                company_id=company_id,
                intent="analyze_risk",
                template_id="credit_assessment",
                options=opts,
            )
        )
        if use_pipeline
        else run_analyze(
            AnalyzeRequest(
                company_id=company_id,
                intent="analyze_risk",
                template_id="credit_assessment",
                options=opts,
            )
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
    # 多 Agent 流水线产出注入报告
    if use_pipeline:
        payload["narrative"] = result.get("narrative") or {}
        payload["disclosures"] = result.get("disclosures") or []
        payload["pipeline_mode"] = result.get("pipeline_mode")
    cid = (result.get("company") or {}).get("id") or company_id
    status = "exported" if confirm_export else "generated"
    report_id = repo.save_report(cid, "credit_assessment", payload, status=status)
    export_path = None
    pdf_path = None
    integrity = None
    if confirm_export:
        out = repo.export_dir() / f"{report_id}_credit.docx"
        export_credit_docx(payload, out)
        export_path = str(out)
        out_pdf = repo.export_dir() / f"{report_id}_credit.pdf"
        export_report_pdf(payload, out_pdf, kind="credit")
        pdf_path = str(out_pdf)
        rec = sign(report_id, payload)
        (repo.export_dir() / f"{report_id}_credit.integrity.json").write_text(
            rec.model_dump_json(), encoding="utf-8"
        )
        integrity = rec.model_dump()

    return {
        "report_id": report_id,
        "status": status,
        "status_label": status_label(status, exported=confirm_export),
        "analysis_title": payload.get("analysis_title"),
        "credit": payload,
        "docx_path": export_path,
        "pdf_path": pdf_path,
        "integrity": integrity,
        "summary": result.get("summary"),
        "company": result.get("company"),
    }
