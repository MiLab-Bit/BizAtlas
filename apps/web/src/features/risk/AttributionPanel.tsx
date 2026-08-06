import { LinkedText, SourceLink, type Citation } from "@/features/sources/SourceLink";
import { cn } from "@/shared/lib/cn";
import { Badge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui";

type Attr = {
  id: string;
  score: number;
  weight: number;
  weighted_contribution?: number;
  share_of_total?: number;
  hit_count?: number;
  hits?: {
    rule_id: string;
    name?: string;
    severity: string;
    message: string;
    explain?: string;
  }[];
  drivers?: {
    name: string;
    value?: number | null;
    tier?: string;
    source?: string | null;
    page?: number | null;
  }[];
  narrative?: string;
};

function fmt(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 10 || Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function dedupeHits(hits: NonNullable<Attr["hits"]>) {
  const seen = new Set<string>();
  const out: NonNullable<Attr["hits"]> = [];
  for (const h of hits) {
    const key = `${h.rule_id}|${h.message}|${h.explain || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(h);
  }
  return out;
}

function SevBadge({ severity }: { severity: string }) {
  const tone =
    severity === "高"
      ? "destructive"
      : severity === "中"
        ? "secondary"
        : "outline";
  return <Badge variant={tone}>{severity}</Badge>;
}

export function AttributionPanel({
  attribution,
  activeDim,
  onSelectDim,
  citations = [],
}: {
  attribution: Attr[];
  activeDim: string | null;
  onSelectDim: (id: string) => void;
  citations?: Citation[];
}) {
  const active = attribution.find((a) => a.id === activeDim) || attribution[0];
  if (!attribution.length) return <p className="text-sm text-muted-foreground">暂无归因</p>;

  const drivers = active?.drivers || [];
  const hits = dedupeHits(active?.hits || []);
  const highCount = hits.filter((h) => h.severity === "高").length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-1.5" role="tablist">
        {attribution.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={a.id === active?.id}
            className={cn(
              "inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors",
              a.id === active?.id
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-muted",
            )}
            onClick={() => onSelectDim(a.id)}
          >
            <span>{a.id}</span>
            <span className="font-mono text-xs opacity-80">{Math.round(a.score)}</span>
          </button>
        ))}
      </div>

      {active ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-xl">
              <p className="text-xs font-medium tracking-wide text-primary">维度归因报告</p>
              <h4 className="mt-1 text-lg font-semibold">{active.id}维度</h4>
              {active.narrative ? (
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {active.narrative}
                </p>
              ) : null}
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-5">
              <div>
                <dt className="text-xs text-muted-foreground">危险度</dt>
                <dd className="font-semibold">{Math.round(active.score)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">权重</dt>
                <dd className="font-semibold">{(active.weight * 100).toFixed(0)}%</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">加权贡献</dt>
                <dd className="font-semibold">{active.weighted_contribution ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">总贡献占比</dt>
                <dd className="font-semibold">{((active.share_of_total ?? 0) * 100).toFixed(1)}%</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">命中 / 高危</dt>
                <dd className="font-semibold">
                  {hits.length} / {highCount}
                </dd>
              </div>
            </dl>
          </div>

          <section className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h5 className="text-sm font-semibold">一、驱动指标</h5>
              <span className="text-xs text-muted-foreground">
                {drivers.length} 项 · 悬停蓝链看溯源
              </span>
            </div>
            {drivers.length === 0 ? (
              <p className="text-sm text-muted-foreground">该维暂无直接指标驱动</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40%]">指标</TableHead>
                    <TableHead className="w-[20%]">取值</TableHead>
                    <TableHead>层级</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {drivers.map((d) => {
                    const c: Citation = {
                      label: d.name,
                      value: d.value,
                      tier: d.tier,
                      id: d.source || undefined,
                      page: d.page,
                    };
                    return (
                      <TableRow key={d.name}>
                        <TableCell className="font-medium">
                          <SourceLink citation={c}>{d.name}</SourceLink>
                        </TableCell>
                        <TableCell className="font-mono tabular-nums">{fmt(d.value)}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{d.tier || "—"}</Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h5 className="text-sm font-semibold">二、命中规则</h5>
              <span className="text-xs text-muted-foreground">{hits.length} 条</span>
            </div>
            {hits.length === 0 ? (
              <p className="text-sm text-muted-foreground">无命中</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[8%]">等级</TableHead>
                    <TableHead className="w-[28%]">规则</TableHead>
                    <TableHead>结论与核对</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {hits.map((h) => (
                    <TableRow key={`${h.rule_id}-${h.message}`}>
                      <TableCell>
                        <SevBadge severity={h.severity} />
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{h.name || h.rule_id}</div>
                        <div className="font-mono text-xs text-muted-foreground">{h.rule_id}</div>
                      </TableCell>
                      <TableCell>
                        <div>
                          <LinkedText text={h.message} citations={citations} />
                        </div>
                        {h.explain ? (
                          <div className="mt-1 text-sm text-muted-foreground">
                            <LinkedText text={h.explain} citations={citations} />
                          </div>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
