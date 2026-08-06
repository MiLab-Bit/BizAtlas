import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Radar, ScanSearch, Upload } from "lucide-react";
import { useState } from "react";
import { AttributionPanel } from "@/features/risk/AttributionPanel";
import { ConflictsPanel } from "@/features/risk/ConflictsPanel";
import { GuaranteeGraph } from "@/features/risk/GuaranteeGraph";
import { IndustryPanel } from "@/features/risk/IndustryPanel";
import { RiskRadar } from "@/features/risk/RiskRadar";
import { StressPanel } from "@/features/risk/StressPanel";
import { LinkedText, type Citation } from "@/features/sources/SourceLink";
import {
  advanceWorkflow,
  createCompany,
  createReport,
  fetchCompanies,
  fetchFixtures,
  postAnalyze,
  startDueDiligence,
  uploadMetrics,
  type AnalyzeData,
  type WorkflowData,
} from "@/shared/lib/api";
import { useUiStore } from "@/shared/store/ui";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  GradeBadge,
  Input,
  NativeSelect,
  PageHeader,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/ui";

export function WorkbenchPage() {
  const queryClient = useQueryClient();
  const { selectedFixture, setSelectedFixture, setAnalyzeContext } = useUiStore();
  const [mode, setMode] = useState<"fixture" | "upload" | "workflow">("fixture");
  const [companyName, setCompanyName] = useState("上传演示企业");
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);
  const [uploadMsg, setUploadMsg] = useState("");
  const [reportMd, setReportMd] = useState<string | null>(null);
  const [exportHint, setExportHint] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null);
  const [wfMsg, setWfMsg] = useState("");
  const [activeDim, setActiveDim] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState("attribution");

  const fixtures = useQuery({ queryKey: ["fixtures"], queryFn: fetchFixtures });
  const companies = useQuery({ queryKey: ["companies"], queryFn: fetchCompanies });

  const analyze = useMutation({
    mutationFn: (id: string) => postAnalyze(id, "analyze_risk", true),
    onSuccess: (data, id) => {
      const fixture =
        id === "healthy" || id === "risky" || id === "defaulted" ? id : null;
      setAnalyzeContext({
        company_id: (data.company?.id as string | undefined) || id,
        fixture_id: fixture,
        grade: data.summary.grade,
        score: data.summary.score,
        rules_hit: data.rules_hit ?? data.risk.hits?.length,
        conflicts: data.risk.quality.conflicts,
        headline: data.summary.headline,
      });
    },
  });
  const report = useMutation({
    mutationFn: (args: {
      id: string;
      confirm: boolean;
      template: "risk_onepager" | "credit_assessment";
    }) => createReport(args.id, args.confirm, args.template),
    onSuccess: (data) => {
      if (data.markdown) setReportMd(data.markdown);
      setExportHint(
        [
          data.pdf_path ? `PDF: ${data.pdf_path}` : "",
          data.docx_path ? `Word: ${data.docx_path}` : "",
          data.export_path ? `MD: ${data.export_path}` : "",
        ]
          .filter(Boolean)
          .join(" · ") || "已生成草稿",
      );
    },
  });

  const result = analyze.data;
  const displayName =
    (result?.company?.name as string | undefined) || companyName || selectedFixture;
  const targetId = mode === "fixture" ? selectedFixture : activeCompanyId;

  async function onUpload(file: File | null) {
    if (!file) return;
    setUploadMsg("上传解析中…");
    try {
      let companyId = activeCompanyId;
      if (!companyId) {
        const created = await createCompany(companyName, "传统建材");
        companyId = created.id;
        setActiveCompanyId(companyId);
        await queryClient.invalidateQueries({ queryKey: ["companies"] });
      }
      const ingested = await uploadMetrics(companyId, file);
      setUploadMsg(
        `已解析 ${ingested.metrics_count} 项（${ingested.parser ?? "csv"}）· ${ingested.filename}`,
      );
      setMode("upload");
      analyze.mutate(companyId);
    } catch (err) {
      setUploadMsg(err instanceof Error ? err.message : String(err));
    }
  }

  function runAnalyze() {
    if (!targetId) return;
    setReportMd(null);
    setExportHint("");
    analyze.mutate(targetId);
  }

  async function wfStart() {
    setWfMsg("启动贷前流程…");
    try {
      const data = await startDueDiligence({ fixture_id: selectedFixture });
      setWorkflow(data);
      setWfMsg(`已启动 · 阶段 ${data.stage}`);
    } catch (err) {
      setWfMsg(err instanceof Error ? err.message : String(err));
    }
  }

  async function wfAdvance(action: string, confirm = false) {
    if (!workflow) return;
    try {
      const data = await advanceWorkflow(workflow.id, action, { confirm });
      setWorkflow(data);
      setWfMsg(`当前阶段：${data.stage}`);
      if (typeof data.report?.markdown_preview === "string") {
        setReportMd(String(data.report.markdown_preview));
      }
    } catch (err) {
      setWfMsg(err instanceof Error ? err.message : String(err));
    }
  }

  const wfGrade = (workflow?.analyze?.summary as { grade?: string } | undefined)?.grade;
  const wfHeadline = (workflow?.analyze?.summary as { headline?: string } | undefined)?.headline;
  const wfScore = (workflow?.analyze?.summary as { score?: number } | undefined)?.score;
  const wfRisk = workflow?.analyze?.risk as AnalyzeData["risk"] | undefined;
  const attribution = (result?.attribution || []) as Parameters<typeof AttributionPanel>[0]["attribution"];
  const citations = (result?.citations || []) as Citation[];

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      <PageHeader
        title="上传即研判，结论可追溯"
        description="数据 + 规则 + 计算，把风险研判压成一次上传。"
      >
        <Tabs value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
          <TabsList>
            <TabsTrigger value="fixture">演示案例</TabsTrigger>
            <TabsTrigger value="upload">上传资料</TabsTrigger>
            <TabsTrigger value="workflow">贷前尽调</TabsTrigger>
          </TabsList>

          <TabsContent value="fixture" className="mt-3">
            <div className="flex flex-wrap items-center gap-2">
              <NativeSelect
                value={selectedFixture}
                onChange={(e) => setSelectedFixture(e.target.value)}
              >
                {(fixtures.data ?? ["healthy", "risky", "defaulted"]).map((id) => (
                  <option key={id} value={id}>
                    {id === "healthy"
                      ? "healthy · 健康"
                      : id === "risky"
                        ? "risky · 风险"
                        : "defaulted · 违约"}
                  </option>
                ))}
              </NativeSelect>
              <Button type="button" disabled={analyze.isPending} onClick={runAnalyze}>
                <ScanSearch />
                {analyze.isPending ? "研判中…" : "帮我看风险"}
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="upload" className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                className="max-w-xs"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
              />
              <Button asChild>
                <label className="cursor-pointer">
                  <Upload />
                  选择 CSV/PDF/TXT
                  <input
                    type="file"
                    accept=".csv,.tsv,.txt,.pdf"
                    hidden
                    onChange={(e) => onUpload(e.target.files?.[0] ?? null)}
                  />
                </label>
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!activeCompanyId}
                onClick={runAnalyze}
              >
                重新研判
              </Button>
            </div>
            {uploadMsg ? <p className="text-sm text-muted-foreground">{uploadMsg}</p> : null}
            {(companies.data?.length ?? 0) > 0 ? (
              <NativeSelect
                value={activeCompanyId ?? ""}
                onChange={(e) => setActiveCompanyId(e.target.value || null)}
              >
                <option value="">最近企业…</option>
                {companies.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            ) : null}
          </TabsContent>

          <TabsContent value="workflow" className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <NativeSelect
                value={selectedFixture}
                onChange={(e) => setSelectedFixture(e.target.value)}
              >
                {(fixtures.data ?? []).map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </NativeSelect>
              <Button type="button" onClick={wfStart}>
                启动贷前尽调
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!workflow?.required_ready}
                onClick={() => wfAdvance("analyze")}
              >
                研判
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!workflow?.analyze}
                onClick={() => wfAdvance("report")}
              >
                出报告
              </Button>
              <Button
                type="button"
                disabled={workflow?.stage !== "awaiting_human"}
                onClick={() => wfAdvance("submit", true)}
              >
                确认提交
              </Button>
            </div>
            {wfMsg ? <p className="text-sm text-muted-foreground">{wfMsg}</p> : null}
          </TabsContent>
        </Tabs>
      </PageHeader>

      {mode === "workflow" && workflow ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>
                {workflow.template_name} · {workflow.stage}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {workflow.stages.map((s) => (
                  <li
                    key={s.id}
                    className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm"
                  >
                    <strong className="block text-foreground">{s.name}</strong>
                    <span className="text-muted-foreground">{s.state}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>资料清单</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {workflow.checklist.map((c) => (
                  <li key={c.id} className="text-sm">
                    <strong className="text-foreground">
                      {c.done ? "✓" : "○"} {c.label}
                    </strong>
                    <small className="mt-0.5 block text-muted-foreground">{c.detail}</small>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>流程结论</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {wfGrade ? (
                <>
                  <GradeBadge grade={wfGrade} />
                  <p className="text-base font-medium">{wfHeadline}</p>
                  <p className="text-sm text-muted-foreground">得分 {wfScore}</p>
                  {wfRisk?.dimensions ? <RiskRadar dimensions={wfRisk.dimensions} /> : null}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">完成研判后显示</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {mode !== "workflow" && result ? (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <Card>
              <CardContent className="space-y-4 pt-5">
                <GradeBadge grade={result.summary.grade} />
                <h2 className="text-2xl font-bold tracking-tight">{displayName}</h2>
                <p className="text-base leading-relaxed text-foreground">
                  <LinkedText text={result.summary.headline} citations={citations} />
                </p>
                {result.summary.headline_meta?.polished ? (
                  <p className="text-xs text-muted-foreground">结论句经 AI 润色 · Number Gate 已通过</p>
                ) : null}
                <p className="text-sm text-muted-foreground">
                  综合危险度 {result.summary.score} · 指标 {result.metrics_count ?? "—"} · 冲突{" "}
                  {result.risk.quality.conflicts}
                  <span className="ml-2">（蓝链为溯源，悬停查看）</span>
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    disabled={!targetId || report.isPending}
                    onClick={() =>
                      report.mutate({ id: targetId!, confirm: false, template: "risk_onepager" })
                    }
                  >
                    一页摘要
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!targetId || report.isPending}
                    onClick={() =>
                      report.mutate({ id: targetId!, confirm: true, template: "risk_onepager" })
                    }
                  >
                    导出 Word/PDF
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!targetId || report.isPending}
                    onClick={() =>
                      report.mutate({
                        id: targetId!,
                        confirm: true,
                        template: "credit_assessment",
                      })
                    }
                  >
                    信用报告 Word/PDF
                  </Button>
                </div>
                {exportHint ? <p className="text-sm text-muted-foreground">{exportHint}</p> : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>五维雷达</CardTitle>
              </CardHeader>
              <CardContent>
                <RiskRadar
                  dimensions={result.risk.dimensions}
                  onDimensionClick={(id) => {
                    setActiveDim(id);
                    setDetailTab("attribution");
                  }}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>明细下钻</CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs value={detailTab} onValueChange={setDetailTab}>
                <TabsList className="flex h-auto flex-wrap justify-start">
                  <TabsTrigger value="attribution">归因</TabsTrigger>
                  <TabsTrigger value="conflicts">冲突</TabsTrigger>
                  <TabsTrigger value="industry">对标</TabsTrigger>
                  <TabsTrigger value="stress">压力</TabsTrigger>
                  <TabsTrigger value="graph">图谱</TabsTrigger>
                  {reportMd ? <TabsTrigger value="report">报告</TabsTrigger> : null}
                </TabsList>
                <TabsContent value="attribution">
                  <AttributionPanel
                    attribution={attribution}
                    activeDim={activeDim}
                    onSelectDim={setActiveDim}
                    citations={citations}
                  />
                </TabsContent>
                <TabsContent value="conflicts">
                  <ConflictsPanel
                    conflicts={result.conflicts as never}
                    count={result.risk.quality.conflicts}
                  />
                </TabsContent>
                <TabsContent value="industry">
                  <IndustryPanel bench={result.industry_benchmark as never} citations={citations} />
                </TabsContent>
                <TabsContent value="stress">
                  <StressPanel stress={result.stress as never} />
                </TabsContent>
                <TabsContent value="graph">
                  {result.graph ? (
                    <GuaranteeGraph
                      nodes={result.graph.nodes as { id: string; name: string; risk?: string }[]}
                      edges={result.graph.edges as { source: string; target: string; rel?: string }[]}
                      note={result.graph.note}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">无图谱</p>
                  )}
                </TabsContent>
                {reportMd ? (
                  <TabsContent value="report">
                    <div className="space-y-1 rounded-lg bg-muted/40 p-4 text-sm leading-relaxed">
                      {reportMd.split("\n").map((line, i) => (
                        <p
                          key={i}
                          className={line.startsWith("#") ? "font-semibold text-foreground" : ""}
                        >
                          <LinkedText text={line || " "} citations={citations} />
                        </p>
                      ))}
                    </div>
                  </TabsContent>
                ) : null}
              </Tabs>
            </CardContent>
          </Card>
        </div>
      ) : null}

      {mode !== "workflow" && !result ? (
        <section className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 px-6 py-16 text-center animate-rise">
          <Radar size={28} className="mb-3 text-primary" strokeWidth={1.75} />
          <p className="text-base font-semibold">尚未研判</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            选择案例后点击「帮我看风险」，或切换到上传资料。
          </p>
        </section>
      ) : null}
    </main>
  );
}
