import { useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { PageHeader, Card, CardContent, CardHeader, CardTitle } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";
import { postCreditDecision, type CreditDecision } from "@/shared/lib/api";

const DECISION_TONE: Record<string, "ok" | "neutral" | "bad"> = {
  APPROVE: "ok",
  APPROVE_WITH_CONDITIONS: "ok",
  MANUAL_REVIEW: "neutral",
  DECLINE: "bad",
  INSUFFICIENT_DATA: "neutral",
};
const GRADE_TONE: Record<string, string> = {
  GREEN: "border-[hsl(var(--grade-green)/0.3)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green",
  YELLOW: "border-[hsl(var(--grade-yellow)/0.3)] bg-[hsl(var(--grade-yellow)/0.1)] text-grade-yellow",
  ORANGE: "border-[hsl(var(--grade-orange)/0.3)] bg-[hsl(var(--grade-orange)/0.1)] text-grade-orange",
  RED: "border-destructive/30 bg-destructive/10 text-destructive",
  BLACK: "border-destructive/40 bg-destructive/15 text-destructive",
  UNRATED: "border-border bg-secondary/70 text-muted-foreground",
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm text-muted-foreground">
      {label}
      {children}
    </label>
  );
}

function DecisionCard({ d }: { d: CreditDecision }) {
  const tone = DECISION_TONE[d.decision] ?? "neutral";
  const limit = d.limit ?? ({} as any);
  const contagion = d.guarantee_contagion ?? ({} as any);
  const comp = d.data_completeness ?? ({} as any);
  return (
    <div className="space-y-4">
      <div
        className={cn(
          "flex flex-wrap items-center justify-between gap-3 rounded-lg border px-5 py-4",
          tone === "ok" && "border-[hsl(var(--grade-green)/0.3)] bg-[hsl(var(--grade-green)/0.08)]",
          tone === "bad" && "border-destructive/30 bg-destructive/10",
          tone === "neutral" && "border-border bg-secondary/60",
        )}
      >
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">授信决策</div>
          <div
            className={cn(
              "text-2xl font-bold",
              tone === "ok" && "text-grade-green",
              tone === "bad" && "text-destructive",
              tone === "neutral" && "text-foreground",
            )}
          >
            {d.decision_label} <span className="text-sm font-normal text-muted-foreground">({d.decision})</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("rounded-full border px-3 py-1 text-sm font-semibold", GRADE_TONE[d.risk_grade] ?? GRADE_TONE.UNRATED)}>
            {d.risk_grade}
          </span>
          <span className="rounded-full border border-border bg-secondary/70 px-3 py-1 text-sm text-muted-foreground">
            风险分 {Math.round((d.risk_score ?? 0) * 100) / 100}
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader><CardTitle className="text-sm text-muted-foreground">建议额度区间</CardTitle></CardHeader>
          <CardContent>
            <div className="text-lg font-semibold text-foreground">
              {limit.suggested_min ?? "—"} ~ {limit.suggested_max ?? "—"}
              <span className="ml-1 text-xs text-muted-foreground">{limit.unit ?? "万元"}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              系数 {limit.ratio_min ?? "—"}~{limit.ratio_max ?? "—"} · 折减 {Math.round((limit.haircut ?? 0) * 100)}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm text-muted-foreground">人工终审闸门</CardTitle></CardHeader>
          <CardContent>
            <div className={cn("text-lg font-semibold", d.manual_gate?.required ? "text-destructive" : "text-grade-green")}>
              {d.manual_gate?.required ? "需人工审批" : "可自动通过"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{d.manual_gate?.approver_role ?? "reviewer"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm text-muted-foreground">担保圈传染暴露</CardTitle></CardHeader>
          <CardContent>
            <div className="text-lg font-semibold text-foreground">{contagion.exposure_level ?? "—"}</div>
            <div className="mt-1 text-xs text-muted-foreground">
              链深 {contagion.chain_depth ?? "—"} · 节点 {contagion.nodes ?? "—"} · 失信 {contagion.dishonest_in_chain?.length ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm text-muted-foreground">数据完整度</CardTitle></CardHeader>
          <CardContent>
            <div className="text-lg font-semibold text-foreground">{Math.round((comp.core_score ?? 0) * 100)}%</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {comp.core_missing?.length ? `缺失 ${comp.core_missing.length} 项` : "核心字段齐全"}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">决策理由</CardTitle></CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {(d.decision_reasons ?? []).map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </CardContent>
      </Card>

      {(d.conditions ?? []).length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">附加授信条件（{d.conditions.length}）</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {d.conditions.map((c) => (
                <div key={c.id} className="flex items-start gap-3 rounded-md border border-border bg-secondary/40 px-3 py-2">
                  <span className="mt-0.5 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-xs text-primary">{c.id}</span>
                  <div>
                    <div className="text-sm font-medium text-foreground">{c.requirement}</div>
                    <div className="text-xs text-muted-foreground">{c.dimension} · 严重度 {c.severity}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function CreditDecisionPage() {
  const [companyId, setCompanyId] = useState("healthy");
  const [amount, setAmount] = useState(1000);
  const [tenor, setTenor] = useState(12);
  const [result, setResult] = useState<CreditDecision | null>(null);

  const mutation = useMutation({
    mutationFn: () => postCreditDecision(companyId.trim(), Number(amount), Number(tenor)),
    onSuccess: (d) => setResult(d),
  });

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-5 py-8">
      <PageHeader
        brand="BizAtlas · 贷前审批"
        title="贷前授信准入决策卡"
        description="聚焦「贷前审批」单一场景：输入企业与授信要素，引擎给出准入决策、建议额度、附加条件与担保圈传染暴露；未知风险显式披露（UNRATED 不视为安全），ORANGE+ 强制人工终审。可试 fixture：healthy / risky / defaulted。"
      />

      <Card>
        <CardHeader><CardTitle>授信申请</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="企业 ID / fixture">
              <input
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                placeholder="healthy / risky / defaulted"
                className="mt-1.5 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
              />
            </Field>
            <Field label="申请额度（万元）">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="mt-1.5 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
              />
            </Field>
            <Field label="期限（月）">
              <input
                type="number"
                value={tenor}
                onChange={(e) => setTenor(Number(e.target.value))}
                className="mt-1.5 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
              />
            </Field>
          </div>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {mutation.isPending ? "计算中…" : "生成决策卡"}
          </button>
          {mutation.isError && (
            <p className="text-sm text-destructive">请求失败：{(mutation.error as Error).message}</p>
          )}
        </CardContent>
      </Card>

      {result && <DecisionCard d={result} />}
    </main>
  );
}
