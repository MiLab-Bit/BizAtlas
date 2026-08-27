import { Badge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui";

type Conflict = {
  metric: string;
  delta: number;
  rel_delta?: number;
  note?: string;
  values: {
    value?: number | null;
    tier?: string;
    source?: string | null;
    source_type?: string | null;
    page?: number | null;
  }[];
};

function fmt(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  return Math.abs(n) >= 10 || Number.isInteger(n) ? String(n) : n.toFixed(4);
}

export function ConflictsPanel({
  conflicts,
  count,
}: {
  conflicts?: Conflict[];
  count?: number;
}) {
  const list = conflicts || [];
  if (!list.length) {
    return (
      <p className="text-sm text-muted-foreground">未发现多源冲突（冲突数 {count ?? 0}）</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary">数据质量</p>
          <h4 className="mt-1 text-lg font-semibold">多源冲突对照</h4>
        </div>
        <dl className="flex gap-6 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">冲突项</dt>
            <dd className="font-semibold">{list.length}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">处理策略</dt>
            <dd className="font-semibold">不自动裁定</dd>
          </div>
        </dl>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[18%]">指标</TableHead>
            <TableHead className="w-[12%]">差值 Δ</TableHead>
            <TableHead>来源对照</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {list.map((c) => (
            <TableRow key={c.metric}>
              <TableCell className="font-medium">{c.metric}</TableCell>
              <TableCell className="font-mono tabular-nums text-destructive">{fmt(c.delta)}</TableCell>
              <TableCell>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>类型</TableHead>
                      <TableHead>来源</TableHead>
                      <TableHead>值</TableHead>
                      <TableHead>层级</TableHead>
                      <TableHead>页</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {c.values.map((v, i) => (
                      <TableRow key={`${v.source}-${i}`}>
                        <TableCell>{v.source_type || "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{v.source || "—"}</TableCell>
                        <TableCell className="font-mono tabular-nums">{fmt(v.value)}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{v.tier || "—"}</Badge>
                        </TableCell>
                        <TableCell className="font-mono tabular-nums">
                          {v.page != null ? v.page : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="text-sm text-muted-foreground">
        研判默认采用主源（上传 / fixture 主表）；冲突仅作提示。
      </p>
    </div>
  );
}
