import {
  GradeBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui";

type Stress = {
  baseline?: { grade: string; score: number; headline: string };
  scenarios?: {
    id: string;
    name: string;
    description: string;
    grade: string;
    score: number;
    delta_score: number;
    headline: string;
  }[];
  worst?: { name: string; grade: string; score: number } | null;
  note?: string;
};

export function StressPanel({ stress }: { stress?: Stress | null }) {
  if (!stress?.scenarios?.length) {
    return <p className="text-sm text-muted-foreground">未跑压力测试</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary">情景分析</p>
          <h4 className="mt-1 text-lg font-semibold">压力测试报告</h4>
        </div>
        <dl className="flex flex-wrap gap-6 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">基线</dt>
            <dd className="mt-1 flex items-center gap-1.5 font-semibold">
              {stress.baseline?.grade ? (
                <GradeBadge grade={stress.baseline.grade} size="sm" />
              ) : (
                "—"
              )}
              {stress.baseline?.score ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">最差情景</dt>
            <dd className="mt-1 flex items-center gap-1.5 font-semibold">
              {stress.worst ? (
                <>
                  <GradeBadge grade={stress.worst.grade} size="sm" />
                  {stress.worst.name}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[10%]">等级</TableHead>
            <TableHead className="w-[22%]">情景</TableHead>
            <TableHead className="w-[12%]">得分</TableHead>
            <TableHead className="w-[12%]">Δ 得分</TableHead>
            <TableHead>冲击说明</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {stress.scenarios.map((s) => (
            <TableRow key={s.id}>
              <TableCell>
                <GradeBadge grade={s.grade} size="sm" />
              </TableCell>
              <TableCell className="font-medium">{s.name}</TableCell>
              <TableCell className="font-mono tabular-nums">{s.score}</TableCell>
              <TableCell
                className={
                  s.delta_score > 0
                    ? "font-mono tabular-nums text-destructive"
                    : "font-mono tabular-nums"
                }
              >
                {s.delta_score >= 0 ? "+" : ""}
                {s.delta_score}
              </TableCell>
              <TableCell className="text-muted-foreground">{s.description}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {stress.note ? <p className="text-sm text-muted-foreground">{stress.note}</p> : null}
    </div>
  );
}
