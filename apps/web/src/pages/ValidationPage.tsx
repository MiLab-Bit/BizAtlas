import { useQuery } from "@tanstack/react-query";
import { PageHeader, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";
import { getBacktestReport, getComplianceStatement } from "@/shared/lib/api";

/**
 * 后端回溯报告在 v5 把 metrics 下的裸数字改成了 {value, ci95, ...} 对象。
 * 页面曾直接调 `.toFixed()` 导致 TypeError 整站白屏。
 * 这里统一用 num() 兼容 v4（数字）与 v5（{value}）两种形态，
 * 任何形态变化都退化成 "—" 而不是抛错。
 */
function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (v && typeof v === "object" && Number.isFinite((v as { value?: unknown }).value)) {
    return (v as { value: number }).value;
  }
  const n = typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

function fixed(v: unknown, digits = 3): string {
  const n = num(v);
  return n == null ? "—" : n.toFixed(digits);
}

function pct(v: unknown): string {
  const n = num(v);
  return n == null ? "—" : `${(n * 100).toFixed(1)}%`;
}

function MetricChip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-bold text-foreground">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** methodology 在 v5 是对象（v4 是字符串数组），两种都渲染，值为对象时展开子项。 */
function MethodologyBlock({ method }: { method: unknown }) {
  const items: Array<[string, unknown]> = Array.isArray(method)
    ? (method as unknown[]).map((v, i) => [`要点 ${i + 1}`, v])
    : method && typeof method === "object"
      ? Object.entries(method as Record<string, unknown>)
      : [];

  if (items.length === 0) {
    return method ? <p className="text-sm text-muted-foreground">{String(method)}</p> : null;
  }
  return (
    <dl className="space-y-2 text-sm">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt className="font-medium text-foreground">{k}</dt>
          <dd className="text-muted-foreground">
            {v && typeof v === "object" ? (
              <ul className="mt-0.5 space-y-0.5 pl-4 text-xs">
                {Object.entries(v as Record<string, unknown>).map(([k2, v2]) => (
                  <li key={k2}>
                    <span className="text-foreground/80">{k2}</span>：{String(v2)}
                  </li>
                ))}
              </ul>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function BacktestSection() {
  const q = useQuery({ queryKey: ["backtest"], queryFn: getBacktestReport });
  if (q.isLoading) return <p className="text-sm text-muted-foreground">加载回溯验证结果…</p>;
  if (q.isError) return <p className="text-sm text-destructive">加载失败：{(q.error as Error).message}</p>;
  const r = (q.data ?? {}) as Record<string, any>;
  const m = (r.metrics ?? {}) as Record<string, any>;
  // v5 把 sample 挪到了 data 顶层；v4 在 metrics.sample 下
  const sampleTotal = num(r.sample?.total_records) ?? num(m.sample?.total) ?? null;
  const ci: unknown[] = Array.isArray(m.auc?.ci95) ? m.auc.ci95 : [];
  const ciText =
    ci.length === 2 && num(ci[0]) != null && num(ci[1]) != null
      ? `95% CI [${fixed(ci[0])}, ${fixed(ci[1])}]`
      : "95% CI 不可用";
  const leadN = num(m.lead_time?.n);

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-foreground">一、风险评分可验证性（历史回溯）</h2>
      {!r.available ? (
        <Card>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">回溯报告尚未生成 / 暂不可用</p>
            <p>原因：{r.reason ?? "未知"}</p>
            <p className="text-xs">说明：本系统不编造验证数字。回溯完成后，此处将展示 AUC / KS / 提前预警期等可复算指标，并随附样本来源与局限说明。</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>版本 {r.version ?? "—"}</span>
            <span>生成于 {r.generated_at ?? "—"}</span>
            <span>样本 {sampleTotal ?? "—"} 家</span>
          </div>
          {r.headline_for_reviewers && (
            <p className="text-sm text-foreground">{String(r.headline_for_reviewers)}</p>
          )}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricChip label="AUC" value={fixed(m.auc)} sub={ciText} />
            <MetricChip label="KS" value={fixed(m.ks)} sub={m.auc?.interpretation ? "区分度" : undefined} />
            <MetricChip
              label="ORANGE+ 命中率"
              value={pct(m.recall_at_orange_plus)}
              sub={`误报率 ${pct(m.false_positive_at_orange_plus)}`}
            />
            <MetricChip
              label="提前预警期"
              value={num(m.lead_time?.mean_years) != null ? `${fixed(m.lead_time.mean_years, 2)} 年` : "—"}
              sub={`中位 ${fixed(m.lead_time?.median_years, 2)} 年 · 样本 ${leadN ?? "—"}`}
            />
          </div>

          {m.auc?.interpretation && (
            <Card>
              <CardHeader><CardTitle className="text-base">指标口径与解读约束</CardTitle></CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                <p>{String(m.auc.interpretation)}</p>
                {m.recall_at_orange_plus?.note && (
                  <p className="mt-2 text-xs">{String(m.recall_at_orange_plus.note)}</p>
                )}
                {m.lead_time?.disclosure && (
                  <p className="mt-2 text-xs">{String(m.lead_time.disclosure)}</p>
                )}
              </CardContent>
            </Card>
          )}

          {m.lead_time?.unit && (
            <p className="text-xs text-muted-foreground">提前预警期单位：{String(m.lead_time.unit)}</p>
          )}

          <Card>
            <CardHeader><CardTitle className="text-base">方法说明</CardTitle></CardHeader>
            <CardContent>
              <MethodologyBlock method={r.methodology} />
            </CardContent>
          </Card>

          {r.disclosure && (
            <Card>
              <CardHeader><CardTitle className="text-base">诚实声明</CardTitle></CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                <p>{String(r.disclosure)}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}

function ComplianceSection() {
  const q = useQuery({ queryKey: ["compliance"], queryFn: getComplianceStatement });
  if (q.isLoading) return <p className="text-sm text-muted-foreground">加载合规声明…</p>;
  if (q.isError) return <p className="text-sm text-destructive">加载失败：{(q.error as Error).message}</p>;
  const r = (q.data ?? {}) as Record<string, any>;
  const pos = (r.positioning ?? {}) as Record<string, any>;
  const recon = (r.reconciliation ?? {}) as Record<string, any>;
  const rows: Array<Record<string, any>> = Array.isArray(recon.rows) ? recon.rows : [];

  // v5 不再直接给 consistent / running_not_declared / declared_not_running，
  // 改为 rows 明细；这里现算，避免把「无依据」当成「不一致」误报。
  const runningNotDeclared = rows.filter((x) => x.runtime_enabled && !x.declared);
  const declaredNotRunning = rows.filter((x) => x.declared && !x.runtime_enabled);
  const runtimeBroken = rows.filter((x) => x.runtime_enabled && x.runtime_ok === false);
  const consistent = rows.length > 0
    ? runningNotDeclared.length === 0 && declaredNotRunning.length === 0
    : recon.checked === true
      ? true
      : Boolean(recon.consistent);

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-foreground">二、数据授权与合规机制</h2>
      <Card>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p><span className="font-medium text-foreground">产品定位：</span>{pos.what_it_is}</p>
          <div>
            <span className="font-medium text-foreground">边界声明：</span>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {(pos.what_it_is_not ?? []).map((x: string, i: number) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
          <p className="text-xs">{pos.boundary_note}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">数据源授权矩阵（{r.source_count ?? (r.sources?.length ?? 0)} 项）</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="border-b border-border px-2 py-1.5">数据源</th>
                <th className="border-b border-border px-2 py-1.5">类别</th>
                <th className="border-b border-border px-2 py-1.5">来源</th>
                <th className="border-b border-border px-2 py-1.5">授权</th>
                <th className="border-b border-border px-2 py-1.5">个人信息</th>
                <th className="border-b border-border px-2 py-1.5">用途限制</th>
              </tr>
            </thead>
            <tbody>
              {(r.sources ?? []).map((s: any) => (
                <tr key={s.id} className="align-top">
                  <td className="border-b border-border px-2 py-1.5 font-medium text-foreground">{s.name}</td>
                  <td className="border-b border-border px-2 py-1.5">{s.category}</td>
                  <td className="border-b border-border px-2 py-1.5">{s.provenance}</td>
                  <td className="border-b border-border px-2 py-1.5">{s.authorization}</td>
                  <td className="border-b border-border px-2 py-1.5">{s.contains_personal_info}</td>
                  <td className="border-b border-border px-2 py-1.5">{s.usage_limit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            运行时对账（声明 vs 实际启用{rows.length > 0 ? ` · 共 ${rows.length} 项` : ""}）
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {rows.length === 0 ? (
            <p className="text-muted-foreground">
              后端未提供对账明细。{recon.checked ? "已声明对账已执行。" : ""}
            </p>
          ) : (
            <>
              <div
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium",
                  consistent
                    ? "border-[hsl(var(--grade-green)/0.3)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green"
                    : "border-destructive/30 bg-destructive/10 text-destructive",
                )}
              >
                {consistent
                  ? `✓ 声明与实际启用一致（${rows.length}/${rows.length}）`
                  : `⚠ 存在不一致：${runningNotDeclared.length + declaredNotRunning.length} 项`}
              </div>

              {runningNotDeclared.length > 0 && (
                <div>
                  <p className="font-medium text-destructive">
                    运行时已启用但未声明（{runningNotDeclared.length}）：
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted-foreground">
                    {runningNotDeclared.map((x) => (
                      <li key={String(x.id)}>
                        <span className="text-foreground">{x.name ?? x.id}</span>
                        {x.runtime_message ? ` — ${x.runtime_message}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {declaredNotRunning.length > 0 && (
                <div>
                  <p className="font-medium text-muted-foreground">
                    已声明但未启用（{declaredNotRunning.length}）：
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted-foreground">
                    {declaredNotRunning.map((x) => (
                      <li key={String(x.id)}>
                        <span className="text-foreground">{x.name ?? x.id}</span>
                        {x.authorization ? ` — 授权：${x.authorization}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {runtimeBroken.length > 0 && (
                <div>
                  <p className="font-medium text-destructive">
                    已启用但运行异常（{runtimeBroken.length}）：
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted-foreground">
                    {runtimeBroken.map((x) => (
                      <li key={String(x.id)}>
                        <span className="text-foreground">{x.name ?? x.id}</span>
                        {x.runtime_message ? ` — ${x.runtime_message}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer select-none">展开全部对账明细</summary>
                <table className="mt-2 w-full border-collapse">
                  <thead>
                    <tr className="text-left">
                      <th className="border-b border-border px-2 py-1">数据源</th>
                      <th className="border-b border-border px-2 py-1">已声明</th>
                      <th className="border-b border-border px-2 py-1">运行时启用</th>
                      <th className="border-b border-border px-2 py-1">运行时状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((x) => (
                      <tr key={String(x.id)}>
                        <td className="border-b border-border px-2 py-1 text-foreground">{x.name ?? x.id}</td>
                        <td className="border-b border-border px-2 py-1">{x.declared ? "✓" : "—"}</td>
                        <td className="border-b border-border px-2 py-1">{x.runtime_enabled ? "✓" : "—"}</td>
                        <td className="border-b border-border px-2 py-1">{x.runtime_message || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </>
          )}
        </CardContent>
      </Card>

      {r.governance && (
        <Card>
          <CardHeader><CardTitle className="text-base">治理与免责</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <ul className="list-disc space-y-1 pl-5">
              {(r.governance.mechanism ?? []).map((m: string, i: number) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
            {r.governance.limitation && <p className="text-xs">{r.governance.limitation}</p>}
            {r.disclaimer && <p className="text-xs">{r.disclaimer}</p>}
          </CardContent>
        </Card>
      )}

      {Array.isArray(r.limitations) && r.limitations.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">能力边界与局限</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {r.limitations.map((x: any, i: number) => (
                <li key={i}>{typeof x === "string" ? x : String(x?.item ?? JSON.stringify(x))}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </section>
  );
}

export function ValidationPage() {
  return (
    <main className="mx-auto w-full max-w-5xl space-y-8 px-5 py-8">
      <PageHeader
        brand="BizAtlas · 验证与合规"
        title="风险评分可验证性 & 数据合规"
        description="以可复算的历史回溯验证评分有效性，并以「声明—运行时对账」机制落实数据授权与合规，缺则显式披露、不编造数字。"
      />
      <BacktestSection />
      <ComplianceSection />
    </main>
  );
}
