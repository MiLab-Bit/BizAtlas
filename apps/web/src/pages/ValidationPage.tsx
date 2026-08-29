import { useQuery } from "@tanstack/react-query";
import { PageHeader, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";
import { getBacktestReport, getComplianceStatement } from "@/shared/lib/api";

function MetricChip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/40 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-bold text-foreground">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function BacktestSection() {
  const q = useQuery({ queryKey: ["backtest"], queryFn: getBacktestReport });
  if (q.isLoading) return <p className="text-sm text-muted-foreground">加载回溯验证结果…</p>;
  if (q.isError) return <p className="text-sm text-destructive">加载失败：{(q.error as Error).message}</p>;
  const r = q.data as any;
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-foreground">一、风险评分可验证性（历史回溯）</h2>
      {!r?.available ? (
        <Card>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">回溯报告尚未生成 / 暂不可用</p>
            <p>原因：{r?.reason ?? "未知"}</p>
            <p className="text-xs">说明：本系统不编造验证数字。回溯完成后，此处将展示 AUC / KS / 提前预警期等可复算指标，并随附样本来源与局限说明。</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{r.method}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricChip
              label="AUC"
              value={r.metrics.auc?.toFixed(3) ?? "—"}
              sub={`95% CI [${r.metrics.auc_ci?.[0]?.toFixed(3)}, ${r.metrics.auc_ci?.[1]?.toFixed(3)}]`}
            />
            <MetricChip label="KS" value={r.metrics.ks?.toFixed(3) ?? "—"} sub={r.metrics.auc_direction} />
            <MetricChip
              label="ORANGE+ 命中率"
              value={`${Math.round((r.metrics.recall_at_orange_plus ?? 0) * 100)}%`}
              sub={`误报率 ${Math.round((r.metrics.false_positive_at_orange_plus ?? 0) * 100)}%`}
            />
            <MetricChip
              label="提前预警期"
              value={r.metrics.lead_time?.mean_years != null ? `${r.metrics.lead_time.mean_years} 年` : "N/A"}
              sub={`中位 ${r.metrics.lead_time?.median_years ?? "—"} · 样本 ${r.metrics.sample?.total ?? "?"}`}
            />
          </div>
          {Array.isArray(r.caveats) && r.caveats.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-base">方法局限与诚实声明</CardTitle></CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {r.caveats.map((c: string, i: number) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
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
  const r = q.data as any;
  const pos = r?.positioning ?? {};
  const recon = r?.reconciliation ?? {};
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
        <CardHeader><CardTitle className="text-base">数据源授权矩阵（{r?.source_count ?? (r?.sources?.length ?? 0)} 项）</CardTitle></CardHeader>
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
              {(r?.sources ?? []).map((s: any) => (
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
          <CardTitle className="text-base">运行时对账（声明 vs 实际启用）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium",
              recon.consistent
                ? "border-[hsl(var(--grade-green)/0.3)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green"
                : "border-destructive/30 bg-destructive/10 text-destructive",
            )}
          >
            {recon.consistent ? "✓ 声明与实际启用一致" : "⚠ 存在不一致"}
          </div>
          {Array.isArray(recon.running_not_declared) && recon.running_not_declared.length > 0 && (
            <p className="text-destructive">运行时已启用但未声明：{recon.running_not_declared.join(", ")}</p>
          )}
          {Array.isArray(recon.declared_not_running) && recon.declared_not_running.length > 0 && (
            <p className="text-muted-foreground">已声明但未启用：{recon.declared_not_running.join(", ")}</p>
          )}
        </CardContent>
      </Card>

      {r?.governance && (
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
