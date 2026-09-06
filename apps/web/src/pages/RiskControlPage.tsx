import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shield, AlertTriangle, Activity, FileSearch } from "lucide-react";
import { fetchRisk } from "@/shared/lib/api";

const SCALE_TONE: Record<string, string> = {
  AAA: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600",
  AA: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600",
  A: "border-lime-500/40 bg-lime-500/10 text-lime-600",
  BBB: "border-yellow-500/40 bg-yellow-500/10 text-yellow-600",
  BB: "border-yellow-500/40 bg-yellow-500/10 text-yellow-600",
  B: "border-orange-500/40 bg-orange-500/10 text-orange-600",
  CCC: "border-red-500/40 bg-red-500/10 text-red-600",
  CC: "border-red-500/40 bg-red-500/10 text-red-600",
  C: "border-rose-600/40 bg-rose-600/10 text-rose-700",
  D: "border-rose-700/50 bg-rose-700/15 text-rose-800",
};

const GRADE_TONE: Record<string, string> = {
  GREEN: "text-emerald-600",
  YELLOW: "text-yellow-600",
  ORANGE: "text-orange-600",
  RED: "text-red-600",
  BLACK: "text-rose-800",
  UNRATED: "text-muted-foreground",
};

function Bar({ value, tone }: { value: number; tone: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function RiskControlPage() {
  const [input, setInput] = useState("co-demo-600519");
  const [companyId, setCompanyId] = useState("co-demo-600519");

  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ["risk-control", companyId],
    queryFn: () => fetchRisk(companyId),
    retry: 1,
  });

  const risk = data?.risk;
  const modules = risk?.modules;
  const distress = modules?.distress;
  const behavioral = modules?.behavioral;
  const reasons = modules?.reason_codes || [];
  const dims = risk?.dimensions || [];

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-primary text-primary-foreground">
          <Shield size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">风控体系 · B-RCF v2.0.0</h1>
          <p className="text-sm text-muted-foreground">
            银行式多源融合：规则严重度 + 财务困境（Altman/Ohlson/Beneish） + 商业行为（D&B/FICO-SBSS） + 10 级主标尺
          </p>
        </div>
      </div>

      <form
        className="mb-6 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) setCompanyId(input.trim());
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">企业 ID（演示：co-demo-600519 / 002594 / 000002 / 600340）</span>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="w-80 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
            placeholder="co-demo-600519"
          />
        </label>
        <button
          type="submit"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
        >
          运行风控
        </button>
      </form>

      {isLoading && <div className="text-sm text-muted-foreground">风控计算中…</div>}
      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          计算失败：{(error as Error)?.message}
        </div>
      )}

      {risk && (
        <div className="flex flex-col gap-6">
          {/* 顶部：企业 + 主标尺 + 综合分 */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">企业</div>
              <div className="mt-1 text-lg font-semibold text-foreground">
                {data?.company?.name || risk.company_id}
              </div>
              <div className="text-xs text-muted-foreground">{data?.company?.industry || risk.company_id}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">银行主标尺</div>
              <div className={`mt-1 inline-block rounded-md border px-3 py-1 text-2xl font-bold ${SCALE_TONE[risk.master_scale || "D"] || ""}`}>
                {risk.master_scale || "—"}
              </div>
              <div className={`ml-2 text-sm font-medium ${GRADE_TONE[risk.grade] || ""}`}>{risk.grade}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">综合风险分 / PD</div>
              <div className="mt-1 text-2xl font-bold text-foreground">{risk.score?.toFixed(1)}</div>
              <div className="text-sm text-muted-foreground">
                PD ≈ {risk.pd != null ? (risk.pd * 100).toFixed(2) + "%" : "—"}
              </div>
            </div>
          </div>

          {/* 五维规则分 */}
          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Activity size={15} /> 规则严重度五维
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {dims.map((d: any) => (
                <div key={d.id}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-foreground">{d.id}</span>
                    <span className="text-muted-foreground">{d.score?.toFixed(1)} · w{d.weight}</span>
                  </div>
                  <Bar value={d.score || 0} tone="bg-primary" />
                </div>
              ))}
            </div>
          </section>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* 财务困境 */}
            <section className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileSearch size={15} /> 财务困境诊断
              </h2>
              {distress?.models?.altman ? (
                <div className="mb-2 text-sm">
                  <span className="text-foreground">Altman Z''：</span>
                  <span className="font-mono">{distress.models.altman.z}</span>
                  <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                    {distress.models.altman.zone}
                  </span>
                </div>
              ) : (
                <div className="mb-2 text-sm text-muted-foreground">Altman：N/A（缺原始报表科目）</div>
              )}
              {distress?.models?.ohlson ? (
                <div className="mb-2 text-sm">
                  <span className="text-foreground">Ohlson O-Score：</span>
                  <span className="font-mono">{distress.models.ohlson.o_score}</span>
                  <span className="ml-2 text-muted-foreground">PD {distress.models.ohlson.pd}</span>
                </div>
              ) : (
                <div className="mb-2 text-sm text-muted-foreground">Ohlson：N/A</div>
              )}
              {distress?.models?.beneish?.m_score != null ? (
                <div className="mb-2 text-sm">
                  <span className="text-foreground">Beneish M-Score：</span>
                  <span className="font-mono">{distress.models.beneish.m_score}</span>
                  {distress.models.beneish.manipulation_suspect && (
                    <span className="ml-2 text-rose-600">疑似盈余操纵</span>
                  )}
                </div>
              ) : (
                <div className="mb-2 text-sm text-muted-foreground">Beneish：N/A（缺同比时序变量）</div>
              )}
              {distress?.notes?.length ? (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground">
                  {distress.notes.map((n: string, i: number) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              ) : null}
            </section>

            {/* 商业行为 */}
            <section className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <AlertTriangle size={15} /> 商业行为（D&B / FICO-SBSS 式）
              </h2>
              {behavioral?.available ? (
                <>
                  <div className="mb-3 text-sm">
                    <span className="text-foreground">综合行为分：</span>
                    <span className="font-mono text-foreground">{behavioral.composite}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      数据完整度 {behavioral.completeness}
                    </span>
                  </div>
                  {Object.entries(behavioral.scores || {}).map(([dim, v]: any) => (
                    <div key={dim} className="mb-2">
                      <div className="mb-1 flex justify-between text-sm">
                        <span className="text-foreground">{dim}</span>
                        <span className="text-muted-foreground">{v == null ? "N/A" : v}</span>
                      </div>
                      <Bar value={v ?? 0} tone="bg-orange-500" />
                    </div>
                  ))}
                  {behavioral.data_gap?.length ? (
                    <div className="mt-2 text-xs text-muted-foreground">
                      数据缺口：{behavioral.data_gap.join("、")}
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="text-sm text-muted-foreground">无已采集行为信号</div>
              )}
            </section>
          </div>

          {/* reason codes */}
          <section className="rounded-xl border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">FICO 式 Reason Codes（Top 驱动因子）</h2>
            {reasons.length ? (
              <ol className="flex flex-col gap-2">
                {reasons.map((r: any, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                      {i + 1}
                    </span>
                    <span className="text-foreground">{r.factor}</span>
                    <span className="ml-auto rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground">
                      {r.dimension}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="text-sm text-muted-foreground">无显著驱动因子</div>
            )}
          </section>

          {risk.headline ? (
            <div className="rounded-lg border border-border bg-secondary/40 p-3 text-sm text-foreground">
              {risk.headline}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
