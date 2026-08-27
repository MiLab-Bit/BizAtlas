import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { activateRule, fetchRules, postNlRule } from "@/shared/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  PageHeader,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/ui";

export function RulesPage() {
  const rules = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const [nlText, setNlText] = useState("如果商誉占比超 25% 就预警");
  const [msg, setMsg] = useState("");
  const [pilotId, setPilotId] = useState<string | null>(null);

  async function addRule() {
    setMsg("LLM 编写中…");
    try {
      const rule = await postNlRule(nlText);
      setPilotId(String(rule.id));
      const src = String(rule.source ?? "");
      setMsg(
        `已入库 pilot：${String(rule.id)} · ${String(rule.name ?? "")}` +
          (src.includes("llm") ? "（LLM）" : "（离线）"),
      );
      await rules.refetch();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  async function activate() {
    if (!pilotId) return;
    try {
      await activateRule(pilotId);
      setMsg(`已激活：${pilotId}`);
      setPilotId(null);
      await rules.refetch();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      <PageHeader
        title="规则中心"
        description="外置 YAML · 自然语言由 LLM 编写为 pilot 规则 · 确认后才计分。"
        compact
        actions={
          <>
            <Input
              className="min-w-[240px] flex-1"
              value={nlText}
              onChange={(e) => setNlText(e.target.value)}
            />
            <Button type="button" onClick={addRule}>
              LLM 编写规则
            </Button>
            <Button type="button" variant="outline" disabled={!pilotId} onClick={activate}>
              激活计分
            </Button>
          </>
        }
      >
        {msg ? <p className="text-sm text-muted-foreground">{msg}</p> : null}
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle>规则库（{rules.data?.length ?? 0}）</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>名称</TableHead>
                <TableHead>维度</TableHead>
                <TableHead>严重度</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>计分</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(rules.data ?? []).map((r) => (
                <TableRow key={String(r.id)}>
                  <TableCell>{String(r.id)}</TableCell>
                  <TableCell>{String(r.name ?? "")}</TableCell>
                  <TableCell>{String(r.dimension ?? "")}</TableCell>
                  <TableCell>{String(r.severity ?? "")}</TableCell>
                  <TableCell>{String(r.status ?? "active")}</TableCell>
                  <TableCell>{r.contribute_to_score === false ? "否" : "是"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  );
}
