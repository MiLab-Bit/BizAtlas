import { SourceLink, type Citation } from "@/features/sources/SourceLink";
import { Badge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui";

type Row = {
  metric: string;
  company?: number | null;
  industry_median?: number | null;
  status?: string;
  note?: string;
};

type Bench = {
  industry?: string;
  label?: string;
  rows?: Row[];
  warn_count?: number;
  note?: string;
};

function fmt(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  return Math.abs(n) >= 10 || Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function IndustryPanel({
  bench,
  citations = [],
}: {
  bench?: Bench | null;
  citations?: Citation[];
}) {
  if (!bench?.rows?.length) return <p className="text-sm text-muted-foreground">无行业对标数据</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary">行业对标 · L3</p>
          <h4 className="mt-1 text-lg font-semibold">{bench.label || bench.industry || "行业"}</h4>
        </div>
        <dl className="flex gap-6 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">对标项</dt>
            <dd className="font-semibold">{bench.rows.length}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">警戒</dt>
            <dd className={bench.warn_count ? "font-semibold text-destructive" : "font-semibold"}>
              {bench.warn_count ?? 0}
            </dd>
          </div>
        </dl>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[22%]">指标</TableHead>
            <TableHead className="w-[16%]">企业值</TableHead>
            <TableHead className="w-[16%]">行业中位</TableHead>
            <TableHead className="w-[14%]">状态</TableHead>
            <TableHead>说明</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {bench.rows.map((r) => {
            const warn = r.status?.startsWith("warn");
            const cited = citations.find((c) => c.label === r.metric);
            const link: Citation = cited || {
              label: r.metric,
              value: r.company,
              tier: "L3",
              id: "industry_benchmark",
            };
            return (
              <TableRow key={r.metric} className={warn ? "bg-destructive/5" : undefined}>
                <TableCell className="font-medium">
                  <SourceLink citation={link}>{r.metric}</SourceLink>
                </TableCell>
                <TableCell className="font-mono tabular-nums">{fmt(r.company)}</TableCell>
                <TableCell className="font-mono tabular-nums">{fmt(r.industry_median)}</TableCell>
                <TableCell>
                  <Badge variant={warn ? "destructive" : "secondary"}>
                    {warn ? "警戒" : "正常"}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{r.note || "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {bench.note ? <p className="text-sm text-muted-foreground">{bench.note}</p> : null}
    </div>
  );
}
