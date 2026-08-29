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

// —— 多 Agent 执行迹（调查工作台）——
const AgentTraceSchema = z.object({
  role_key: z.string(),
  label: z.string(),
  status: z.string(),
  mode: z.string(),
  ok: z.boolean(),
  task: z.string(),
  inputs: z.number(),
  outputs: z.number(),
  evidence: z.number(),
  tool_calls: z.array(z.string()),
  notes: z.array(z.string()),
  summary: z.string().optional().default(""),
});

const ToolCallSchema = z.object({
  agent: z.string(),
  agent_label: z.string(),
  name: z.string(),
  kind: z.string(),
  detail: z.string(),
  result: z.string(),
  ok: z.boolean(),
});

const TraceEventSchema = z.object({
  seq: z.number(),
  ts_offset_ms: z.number(),
  agent: z.string(),
  agent_label: z.string(),
  type: z.string(),
  message: z.string(),
  level: z.string(),
});

const EvidenceSchema = z.object({
  id: z.string(),
  label: z.string(),
  dimension: z.string().optional().default(""),
  page: z.number().nullable().optional(),
  tier: z.string().nullable().optional(),
  value: z.number().nullable().optional(),
  confidence: z.number().nullable().optional(),
  source: z.string().optional().default(""),
  kind: z.string(),
});

const TraceSummarySchema = z.object({
  grade: z.string().nullable().optional(),
  score: z.number().nullable().optional(),
  completeness: z.number().nullable().optional(),
  rules_hit: z.number(),
  data_gaps: z.number(),
  research_found: z.number(),
  research_gaps: z.number(),
  disclosures: z.number(),
  pipeline_mode: z.string().nullable().optional(),
  llm_used: z.boolean().optional().default(false),
  dimensions: z.array(z.record(z.unknown())).optional(),
  headline: z.string().optional().default(""),
});

const TraceSchema = z.object({
  task_id: z.string().nullable().optional(),
  company: z.record(z.unknown()).optional(),
  pipeline_status: z.string().optional().default("succeeded"),
  pipeline_mode: z.string().nullable().optional(),
  agents: z.array(AgentTraceSchema),
  tool_calls: z.array(ToolCallSchema),
  events: z.array(TraceEventSchema),
  evidence: z.array(EvidenceSchema),
  summary: TraceSummarySchema,
});

const AnalyzePipelineSchema = AnalyzeSchema.extend({
  trace: TraceSchema,
  pipeline_mode: z.string().nullable().optional(),
  agents: z.record(z.unknown()).optional(),
  narrative: z.record(z.unknown()).optional(),
  disclosures: z.array(z.record(z.unknown())).optional(),
});

export type AgentTrace = z.output<typeof AgentTraceSchema>;
export type ToolCall = z.output<typeof ToolCallSchema>;
export type TraceEvent = z.output<typeof TraceEventSchema>;
export type EvidenceItem = z.output<typeof EvidenceSchema>;
export type TraceSummary = z.output<typeof TraceSummarySchema>;
export type TraceData = z.output<typeof TraceSchema>;
export type AnalyzePipelineData = z.output<typeof AnalyzePipelineSchema>;

// SSE 实时流事件（/v1/analyze/pipeline/stream 逐行推送，供前端实时渲染）
export type PipelineStreamEvent =
  | { type: "task_created"; company_id: string }
  | { type: "agent_start"; role: string; label: string }
  | {
      type: "agent_done";
      role: string;
      label: string;
      ok: boolean;
      mode: string;
      summary: string;
    }
  | {
      type: "done";
      trace: TraceData;
      pipeline_mode: string | null;
      pipeline_status: string;
    };

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function bearerHeader(): Record<string, string> {
  const t = typeof localStorage !== "undefined" ? localStorage.getItem("bizatlas_access_token") : null;
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function getEnvelope<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.output<S>> {
  const headers = { ...bearerHeader(), ...(init?.headers ?? {}) };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
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

export function postAnalyze(
  companyId: string,
  intent = "analyze_risk",
  includeStress = true,
  fast = true,
) {
  return getEnvelope("/v1/analyze", AnalyzeSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: companyId,
      intent,
      message: "帮我看风险",
      template_id: intent === "gen_report" ? "risk_onepager" : null,
      options: {
        include_stress: includeStress && !fast,
        include_kg: true,
        skip_polish: fast,
        fast,
      },
    }),
  });
}

export function postAnalyzePipeline(
  companyId: string,
  intent = "analyze_risk",
  includeStress = true,
  fast = false,
) {
  return getEnvelope("/v1/analyze/pipeline", AnalyzePipelineSchema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: companyId,
      intent,
      message: "进入调查",
      template_id: null,
      options: {
        include_stress: includeStress && !fast,
        include_kg: true,
        skip_polish: fast,
        fast,
      },
    }),
  });
}

export function subscribePipelineStream(
  companyId: string,
  intent = "analyze_risk",
  handlers: {
    onEvent: (ev: PipelineStreamEvent) => void;
    onEnd?: () => void;
    onError?: (err: Event) => void;
  },
  fast = true,
): EventSource {
  const params = new URLSearchParams({
    company_id: companyId,
    task: intent,
    fast: fast ? "true" : "false",
  });
  const es = new EventSource(
    `${API_BASE}/v1/analyze/pipeline/stream?${params.toString()}`,
  );
  es.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data) as PipelineStreamEvent;
      handlers.onEvent(ev);
    } catch {
      /* 忽略畸形帧 */
    }
  };
  es.addEventListener("end", () => {
    handlers.onEnd?.();
    es.close();
  });
  es.onerror = (e) => {
    handlers.onError?.(e);
    es.close();
  };
  return es;
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

// —— 邮箱验证 / 密码找回（身份基础设施）——
const AuthUserLoose = z.record(z.unknown());

export function requestVerification(email: string) {
  return getEnvelope(
    "/v1/auth/request-verification",
    z.object({ sent: z.boolean().optional() }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    },
  );
}

export function verifyEmail(token: string) {
  return getEnvelope(
    `/v1/auth/verify-email?token=${encodeURIComponent(token)}`,
    z.object({ user: AuthUserLoose.nullable().optional() }),
  );
}

export function requestPasswordReset(email: string) {
  return getEnvelope(
    "/v1/auth/request-password-reset",
    z.object({ sent: z.boolean().optional() }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    },
  );
}

export function resetPassword(token: string, newPassword: string) {
  return getEnvelope(
    "/v1/auth/reset-password",
    z.object({ user: AuthUserLoose.nullable().optional() }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    },
  );
}

// —— 用户自带大模型供应商密钥（模型配置）——
export const ProviderPresetSchema = z.object({
  provider: z.string(),
  label: z.string(),
  baseUrl: z.string(),
  defaultModel: z.string(),
});
export type ProviderPreset = z.output<typeof ProviderPresetSchema>;

export const ModelProviderSchema = z.object({
  id: z.string(),
  name: z.string(),
  provider: z.string(),
  base_url: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  status: z.string(),
  last_error: z.string().nullable().optional(),
  last_tested_at: z.string().nullable().optional(),
  created_at: z.string(),
});
export type ModelProvider = z.output<typeof ModelProviderSchema>;

export function listProviderPresets(): Promise<ProviderPreset[]> {
  return getEnvelope("/v1/auth/model-providers/presets", z.object({ providers: z.array(ProviderPresetSchema) }))
    .then((d) => d.providers);
}

export function listModelProviders(): Promise<ModelProvider[]> {
  return getEnvelope("/v1/auth/model-providers", z.object({ providers: z.array(ModelProviderSchema) }))
    .then((d) => d.providers);
}

export async function testModelProvider(input: {
  provider: string;
  apiKey: string;
  baseUrl?: string;
  model?: string;
}): Promise<{ ok: boolean; latency_ms: number; error?: string; model?: string }> {
  return getEnvelope(
    "/v1/auth/model-providers/test",
    z.object({ ok: z.boolean(), latency_ms: z.number(), error: z.string().optional(), model: z.string().optional() }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function createModelProvider(input: {
  name: string;
  provider: string;
  apiKey: string;
  baseUrl?: string;
  model?: string;
}): Promise<{ provider: ModelProvider; test: Record<string, unknown> }> {
  return getEnvelope(
    "/v1/auth/model-providers",
    z.object({ provider: ModelProviderSchema, test: z.record(z.unknown()) }),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function deleteModelProvider(id: string): Promise<void> {
  await getEnvelope(`/v1/auth/model-providers/${id}`, z.record(z.unknown()), {
    method: "DELETE",
  });
}

// ---- 贷前审批场景聚焦：授信决策卡 + 回溯验证 + 数据合规 ----
export interface CreditDecisionCondition {
  id: string;
  dimension: string;
  requirement: string;
  scenario: string;
  severity: string;
}
export interface CreditDecision {
  scenario: string;
  product: string;
  company: { id: string; name: string; industry: string };
  application: { applied_amount: number; tenor_months: number; unit: string };
  decision: string;
  decision_label: string;
  decision_reasons: string[];
  risk_grade: string;
  risk_score: number;
  manual_gate: { required: boolean; reason: string; approver_role: string };
  limit: {
    currency: string;
    unit: string;
    applied_amount: number;
    ratio_min: number;
    ratio_max: number;
    suggested_min: number;
    suggested_max: number;
    haircut: number;
    haircut_basis: string | null;
    basis: string;
    note: string;
  };
  guarantee_contagion: {
    exposure_level: string;
    chain_depth: number;
    nodes: number;
    edges: number;
    dishonest_in_chain: string[];
    negative_rated_in_chain: number;
    note: string;
  };
  data_completeness: {
    core_score: number;
    core_missing: string[];
    enrich_score: number;
    enrich_missing: string[];
    note: string;
  };
  conditions: CreditDecisionCondition[];
}

export interface BacktestMetrics {
  auc: number;
  auc_ci: [number, number];
  auc_direction: string;
  ks: number;
  recall_at_orange_plus: number;
  false_positive_at_orange_plus: number;
  lead_time?: { mean_years: number | null; median_years: number | null; note: string };
  sample?: { total: number; positive: number; negative: number };
}
export interface BacktestReport {
  available: boolean;
  reason?: string;
  method?: string;
  as_of?: string;
  metrics?: BacktestMetrics;
  caveats?: string[];
  generated_at?: string;
}

export interface ComplianceSource {
  id: string;
  name: string;
  category: string;
  provenance: string;
  authorization: string;
  contains_personal_info: string;
  personal_info_handling: string;
  usage_limit: string;
  retention: string;
  refresh: string;
}
export interface ComplianceStatement {
  version: number;
  updated_at: string;
  applicable_scenario: string;
  positioning: { what_it_is: string; what_it_is_not: string[]; boundary_note: string };
  sources?: ComplianceSource[];
  source_count?: number;
  reconciliation?: { consistent: boolean; running_not_declared: string[]; declared_not_running: string[] };
  governance?: { mechanism: string[]; limitation: string };
  disclaimer?: string;
}

export async function postCreditDecision(
  companyId: string,
  appliedAmount: number,
  tenorMonths: number,
  _runFresh = false,
): Promise<CreditDecision> {
  const data = await getEnvelope("/v1/credit/decision", z.any(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      company_id: companyId,
      applied_amount: appliedAmount,
      tenor_months: tenorMonths,
      skip_polish: true,
      include_stress: false,
    }),
  });
  // API 返回 { decision, analysis }；页面消费扁平 decision 对象
  const decision = (data?.decision ?? data) as CreditDecision;
  if (Array.isArray(decision.conditions)) {
    decision.conditions = decision.conditions.map((c: any) => ({
      ...c,
      requirement: c.requirement ?? c.text ?? "",
    }));
  }
  return decision;
}

export function getBacktestReport(): Promise<BacktestReport> {
  return getEnvelope("/v1/validation/backtest", z.any());
}

export function getComplianceStatement(): Promise<ComplianceStatement> {
  return getEnvelope("/v1/compliance/statement", z.any());
}
