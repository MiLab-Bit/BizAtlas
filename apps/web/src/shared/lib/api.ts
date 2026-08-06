import { z } from "zod";

const EnvelopeSchema = z.object({
  ok: z.boolean(),
  data: z.unknown().nullable(),
  error: z.record(z.unknown()).nullable().optional(),
  meta: z.record(z.unknown()).default({}),
});

const HealthSchema = z.object({
  service: z.string(),
  version: z.string(),
  mode: z.string(),
  db_ok: z.boolean(),
  rules_loaded: z.number(),
  llm_configured: z.boolean().optional().default(false),
  llm_model: z.string().optional().default(""),
  providers: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      enabled: z.boolean(),
      status: z.string(),
      ok: z.boolean(),
      message: z.string().optional().default(""),
    }),
  ),
});

const HitSchema = z.object({
  rule_id: z.string(),
  name: z.string().optional(),
  dimension: z.string().nullish().transform((v) => v ?? ""),
  severity: z.string(),
  message: z.string(),
  explain: z.string().nullish().transform((v) => v ?? ""),
});

const AnalyzeSchema = z.object({
  task_id: z.string(),
  status: z.string(),
  summary: z.object({
    headline: z.string(),
    grade: z.string(),
    score: z.number(),
    headline_meta: z
      .object({
        polished: z.boolean().optional(),
        llm_used: z.boolean().optional(),
        gate_ok: z.boolean().optional(),
      })
      .optional(),
  }),
  risk: z.object({
    grade: z.string(),
    score: z.number(),
    headline: z.string(),
    dimensions: z.array(
      z.object({
        id: z.string(),
        score: z.number(),
        weight: z.number(),
      }),
    ),
    hits: z.array(HitSchema),
    veto: z.object({
      triggered: z.boolean(),
      reason: z.string().nullable(),
    }),
    quality: z.object({
      completeness: z.number(),
      conflicts: z.number(),
      tier_mix: z.record(z.number()),
    }),
  }),
  company: z
    .object({
      id: z.string().optional(),
      name: z.string().optional(),
      industry: z.string().optional(),
      fixture_id: z.string().optional(),
    })
    .passthrough()
    .optional(),
  rules_hit: z.number().optional(),
  report_id: z.string().nullable().optional(),
  onepager: z.record(z.unknown()).nullable().optional(),
  metrics_count: z.number().optional(),
  graph: z
    .object({
      nodes: z.array(z.record(z.unknown())),
      edges: z.array(z.record(z.unknown())),
      note: z.string().optional(),
    })
    .nullish(),
  citations: z
    .array(
      z.object({
        id: z.string().optional(),
        label: z.string().optional(),
        page: z.number().nullable().optional(),
        tier: z.string().optional(),
        value: z.number().nullable().optional(),
      }),
    )
    .optional(),
  attribution: z.array(z.record(z.unknown())).optional(),
  conflicts: z.array(z.record(z.unknown())).optional(),
  industry_benchmark: z.record(z.unknown()).optional(),
  stress: z.record(z.unknown()).nullable().optional(),
});

const ReportSchema = z.object({
  report_id: z.string().nullable(),
  status: z.string(),
  status_label: z.string().optional(),
  analysis_title: z.string().optional(),
  markdown: z.string().optional(),
  export_path: z.string().nullable().optional(),
  docx_path: z.string().nullable().optional(),
  pdf_path: z.string().nullable().optional(),
  summary: z
    .object({
      headline: z.string(),
      grade: z.string(),
      score: z.number(),
    })
    .optional(),
  company: z.record(z.unknown()).optional(),
  onepager: z.record(z.unknown()).optional(),
  credit: z.record(z.unknown()).optional(),
});

const CompanySchema = z.object({
  id: z.string(),
  name: z.string(),
  industry: z.string().nullable().optional(),
});

const WorkflowSchema = z.object({
  id: z.string(),
  template_id: z.string(),
  template_name: z.string().optional(),
  company_id: z.string(),
  stage: z.string(),
  stages: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      state: z.string(),
    }),
  ),
  checklist: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      required: z.boolean(),
      done: z.boolean(),
      detail: z.string().nullish().transform((v) => v ?? ""),
    }),
  ),
  required_ready: z.boolean(),
  analyze: z.record(z.unknown()).nullable().optional(),
  report: z.record(z.unknown()).nullable().optional(),
  blockers: z.array(z.string()).optional(),
  history: z.array(z.record(z.unknown())).optional(),
});

const RuleSummarySchema = z.object({
  id: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  dimension: z.string().nullable().optional(),
  severity: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  contribute_to_score: z.boolean().optional(),
});

export type HealthData = z.output<typeof HealthSchema>;
export type AnalyzeData = z.output<typeof AnalyzeSchema>;
export type ReportData = z.output<typeof ReportSchema>;
export type WorkflowData = z.output<typeof WorkflowSchema>;

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function getEnvelope<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.output<S>> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail: unknown =
      res.status === 404
        ? "接口不存在，请确认后端已启动且版本包含背调路由"
        : `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      /* ignore */
    }
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    if (res.status === 404 || /not\s*found/i.test(msg)) {
      throw new Error("背调服务未连接，请确认后端 API 已启动后重试");
    }
    throw new Error(msg);
  }
  const json = EnvelopeSchema.parse(await res.json());
  if (!json.ok) {
    throw new Error(String(json.error?.message ?? "request failed"));
  }
  return schema.parse(json.data) as z.output<S>;
}

export function fetchHealth() {
  return getEnvelope("/v1/health", HealthSchema);
}

export function fetchFixtures() {
  return getEnvelope("/v1/fixtures", z.array(z.string()));
}

export function fetchCompanies() {
  return getEnvelope("/v1/companies", z.array(CompanySchema));
}

export function createCompany(name: string, industry = "") {
  return getEnvelope("/v1/companies", CompanySchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, industry }),
  });
}

export function postAnalyze(companyId: string, intent = "analyze_risk", includeStress = true) {
  return getEnvelope("/v1/analyze", AnalyzeSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: companyId,
      intent,
      message: "帮我看风险",
      template_id: intent === "gen_report" ? "risk_onepager" : null,
      options: { include_stress: includeStress, include_kg: true },
    }),
  });
}

export async function uploadMetrics(companyId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return getEnvelope(
    `/v1/companies/${companyId}/documents`,
    z.object({
      document_id: z.string(),
      filename: z.string(),
      metrics_count: z.number(),
      parser: z.string().optional(),
      metrics: z.array(z.record(z.unknown())),
    }),
    { method: "POST", body: form },
  );
}

export function createReport(
  companyId: string,
  confirm = false,
  templateId: "risk_onepager" | "credit_assessment" = "risk_onepager",
) {
  return getEnvelope("/v1/reports", ReportSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: companyId,
      template_id: templateId,
      confirm,
    }),
  });
}

export function startDueDiligence(body: {
  fixture_id?: string;
  company_id?: string;
  name?: string;
}) {
  return getEnvelope("/v1/workflows/due-diligence", WorkflowSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function advanceWorkflow(
  workflowId: string,
  action: string,
  opts?: { confirm?: boolean; manual_flags?: Record<string, boolean> },
) {
  return getEnvelope(`/v1/workflows/${workflowId}/advance`, WorkflowSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      confirm: opts?.confirm ?? false,
      manual_flags: opts?.manual_flags,
    }),
  });
}

export function postNlRule(text: string) {
  return getEnvelope("/v1/rules/from-nl", z.record(z.unknown()), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, activate: false }),
  });
}

export function activateRule(ruleId: string) {
  return getEnvelope(`/v1/rules/${ruleId}/activate?confirm=true`, z.record(z.unknown()), {
    method: "POST",
  });
}

export function fetchRules() {
  return getEnvelope("/v1/rules", z.array(RuleSummarySchema));
}

export function fetchReportsList() {
  return getEnvelope(
    "/v1/reports-list",
    z.array(
      z.object({
        id: z.string(),
        company_id: z.string(),
        company_name: z.string().optional(),
        template_id: z.string().nullable().optional(),
        kind: z.string().optional(),
        title: z.string(),
        grade: z.string().nullable().optional(),
        headline: z.string().nullable().optional(),
        status: z.string().nullable().optional(),
        status_label: z.string().optional(),
        created_at: z.string().nullable().optional(),
      }),
    ),
  );
}

export async function fetchReportMarkdown(reportId: string) {
  const res = await fetch(`${API_BASE}/v1/reports/${reportId}/markdown`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

export function postChat(
  message: string,
  opts?: {
    companyId?: string | null;
    fixtureId?: string | null;
    context?: Record<string, unknown>;
  },
) {
  return getEnvelope(
    "/v1/chat",
    z.object({
      type: z.string(),
      intent: z.string().optional(),
      intent_source: z.string().optional(),
      answer: z.string().optional(),
      citations: z.array(z.record(z.unknown())).optional(),
      rule: z.record(z.unknown()).optional(),
      confidence: z.number().optional(),
      llm_used: z.boolean().optional(),
      summary: z.record(z.unknown()).optional(),
      analyze: z.record(z.unknown()).optional(),
      report: z.record(z.unknown()).optional(),
    }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        fixture_id: opts?.fixtureId || undefined,
        company_id: opts?.companyId || opts?.fixtureId || undefined,
        context: opts?.context || undefined,
      }),
    },
  );
}

const BackgroundStartSchema = z.object({
  company_id: z.string(),
  company_name: z.string(),
  fixture_id: z.string().nullable().optional(),
  matched_fixture: z.boolean().optional(),
  tianyancha: z
    .object({
      ok: z.boolean().optional(),
      configured: z.boolean().optional(),
      message: z.string().optional().nullable(),
    })
    .optional(),
  summary: z.record(z.unknown()).nullable().optional(),
  message: z.string().optional(),
  llm_used: z.boolean().optional(),
  gate_ok: z.boolean().optional(),
});

export function startBackgroundCheck(companyName: string, industry = "") {
  return getEnvelope("/v1/background/start", BackgroundStartSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name: companyName, industry }),
  });
}

export function postBackgroundChat(args: {
  companyName: string;
  message: string;
  companyId?: string | null;
  fixtureId?: string | null;
  history?: { role: string; content: string }[];
}) {
  return getEnvelope(
    "/v1/background/chat",
    z.object({
      answer: z.string(),
      llm_used: z.boolean().optional(),
      gate_ok: z.boolean().optional(),
      facts: z.record(z.unknown()).optional(),
    }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_name: args.companyName,
        message: args.message,
        company_id: args.companyId || undefined,
        fixture_id: args.fixtureId || undefined,
        history: args.history,
      }),
    },
  );
}
