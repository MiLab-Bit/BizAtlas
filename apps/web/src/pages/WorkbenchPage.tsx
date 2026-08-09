import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Network, Radar, ScanSearch, Upload, FileText, Workflow, Database, Zap } from "lucide-react";
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
import { cn } from "@/shared/lib/cn";

/** 三种模式的元信息 */
const MODES = {
  fixture: {
    icon: Database,
    title: "演示案例",
    desc: "使用内置案例快速体验完整研判流程，查看五维雷达、归因分析等全部功能。",
    label: "演示案例",
  },
  upload: {
    icon: Upload,
    title: "上传资料",
    desc: "上传 CSV/PDF/TXT 财务或经营数据，自动解析并生成风险报告。",
    label: "上传资料",
  },
  workflow: {
    icon: Workflow,
    title: "贷前尽调流程",
    desc: "按标准贷前尽调流程分阶段推进：启动 → 研判 → 出报告 → 确认提交。",
    label: "贷前尽调",
  },
} as const;

export function WorkbenchPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { selectedFixture, setSelectedFixture, setAnalyzeContext } = useUiStore();
  const [mode, setMode] = useState<"fixture" | "upload" | "workflow" | null>(null);
  const [companyName, setCompanyName] = useState("");
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
        const created = await createCompany(companyName || "未命名企业", "传统建材");
        companyId = created.id;
        setActiveCompanyId(companyId);
        await queryClient.invalidateQueries({ queryKey: ["companies"] });
      }
      const ingested = await uploadMetrics(companyId, file);
      setUploadMsg(
        `已解析 ${ingested.metrics_count} 项（${ingested.parser ?? "csv"}）· ${ingested.filename}`,
      );
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

  /* ================================================================
   * 渲染
   * ================================================================ */

  // 有结果时直接展示结果区（不管 mode 选择状态）
  if (result && mode !== "workflow") {
    return <ResultView {...{
      result, displayName, targetId, report, exportHint, navigate,
      activeDim, setActiveDim, detailTab, setDetailTab, reportMd,
      attribution, citations, onReset: () => { analyze.reset(); setMode(null); setReportMd(null); }}
    } />;
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      <PageHeader
        title="风险分析工作台"
        description="选择一种方式开始企业风险研判，结果支持导出和深度下钻。"
      />

      {/* ====== 模式选择（无结果时显示）====== */}
      {!result && !mode && (
        <section className="grid gap-4 sm:grid-cols-3">
          {(Object.entries(MODES) as [keyof typeof MODES, typeof MODES[keyof typeof MODES]][]).map(
            ([key, { icon: Icon, title, desc }]) => (
              <button
                key={key}
                type="button"
                onClick={() => setMode(key)}
                className="group flex flex-col gap-3 rounded-xl border border-border/70 bg-card p-5 text-left transition-all hover:border-primary/30 hover:shadow-md"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                  <Icon size={20} />
                </div>
                <div>
                  <div className="text-base font-semibold text-foreground">{title}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted-foreground">{desc}</div>
                </div>
                <span className="mt-auto inline-flex w-fit items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                  <Zap size={12} />
                  进入 →
                </span>
              </button>
            ),
          )}
        </section>
      )}

      {/* ====== 演示案例操作区 ====== */}
      {mode === "fixture" && !result && (
        <Card className="animate-rise">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database size={18} className="text-primary" />
              演示案例
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              选择一个内置案例，点击按钮即可触发完整的五维风险研判流程。
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <NativeSelect
                value={selectedFixture}
                onChange={(e) => setSelectedFixture(e.target.value)}
                className="max-w-xs"
              >
                {(fixtures.data ?? ["healthy", "risky", "defaulted"]).map((id) => (
                  <option key={id} value={id}>
                    {id === "healthy"
                      ? "healthy · 健康（低风险）"
                      : id === "risky"
                        ? "risky · 风险（中高风险）"
                        : "defaulted · 违约（已暴雷）"}
                  </option>
                ))}
              </NativeSelect>
              <Button type="button" disabled={analyze.isPending} onClick={runAnalyze}>
                <ScanSearch />
                {analyze.isPending ? "研判中…" : "开始研判"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMode(null)}
              >
                ← 返回选择
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ====== 上传资料操作区 ====== */}
      {mode === "upload" && !result && (
        <Card className="animate-rise">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload size={18} className="text-primary" />
              上传资料
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              填写企业名称并上传财务数据文件（CSV/PDF/TXT），系统将自动解析指标并完成风险研判。
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Input
                className="max-w-xs"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="企业名称"
              />
              <Button asChild>
                <label className="cursor-pointer">
                  <Upload size={14} />
                  选择文件
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
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setMode(null)}
              >
                ← 返回选择
              </Button>
            </div>
            {uploadMsg ? <p className="text-sm text-muted-foreground">{uploadMsg}</p> : null}
            {(companies.data?.length ?? 0) > 0 ? (
              <div className="pt-1">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">最近上传的企业：</p>
                <NativeSelect
                  value={activeCompanyId ?? ""}
                  onChange={(e) => setActiveCompanyId(e.target.value || null)}
                >
                  <option value="">选择企业…</option>
                  {companies.data?.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </NativeSelect>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* ====== 贷前尽调操作区 ====== */}
      {mode === "workflow" && (
        <>
          <Card className="animate-rise">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Workflow size={18} className="text-primary" />
                贷前尽调流程
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                按标准贷前尽调流程分阶段推进。选择案例后依次执行各阶段。
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <NativeSelect
                  value={selectedFixture}
                  onChange={(e) => setSelectedFixture(e.target.value)}
                >
                  {(fixtures.data ?? []).map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </NativeSelect>
                <Button type="button" onClick={wfStart}>启动流程</Button>
                <Button type="button" variant="outline" disabled={!workflow?.required_ready} onClick={() => wfAdvance("analyze")}>
                  研判
                </Button>
                <Button type="button" variant="outline" disabled={!workflow?.analyze} onClick={() => wfAdvance("report")}>
                  出报告
                </Button>
                <Button type="button" disabled={workflow?.stage !== "awaiting_human"} onClick={() => wfAdvance("submit", true)}>
                  确认提交
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setMode(null)}>
                  ← 返回选择
                </Button>
              </div>
              {wfMsg ? <p className="text-sm text-muted-foreground">{wfMsg}</p> : null}
            </CardContent>
          </Card>

          {/* 工作流详情卡片 */}
          {workflow ? (
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="md:col-span-2">
                <CardHeader>
                  <CardTitle>{workflow.template_name} · 当前阶段：{workflow.stage}</CardTitle>
                </CardHeader>
                <CardContent>
                  <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {workflow.stages.map((s) => (
                      <li key={s.id} className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
                        <strong className="block text-foreground">{s.name}</strong>
                        <span className="text-muted-foreground">{s.state}</span>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>资料清单</CardTitle></CardHeader>
                <CardContent>
                  <ul className="space-y-2">
                    {workflow.checklist.map((c) => (
                      <li key={c.id} className="text-sm">
                        <strong className="text-foreground">{c.done ? "\u2713" : "\u25CB"} {c.label}</strong>
                        <small className="mt-0.5 block text-muted-foreground">{c.detail}</small>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>流程结论</CardTitle></CardHeader>
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
        </>
      )}

      {/* 空状态提示 */}
      {!mode && !result && (
        <section className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 px-6 py-12 text-center animate-rise">
          <Radar size={32} className="mb-3 text-primary/60" strokeWidth={1.5} />
          <p className="text-base font-semibold text-foreground">选择上方一种方式开始</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            漄示案例可快速体验全流程；上传资料适用于自有数据；贷前尽调是标准化审批流。
          </p>
        </section>
      )}
    </main>
  );
}

/* ================================================================
 * 结果视图（独立组件，有结果时全屏展示）
 * ================================================================ */
function ResultView({
  result, displayName, targetId, report, exportHint, navigate,
  activeDim, setActiveDim, detailTab, setDetailTab, reportMd,
  attribution, citations, onReset,
}: {
  result: NonNullable<ReturnType<typeof useMutation>["data"]>;
  displayName: string;
  targetId: string | null;
  report: ReturnType<typeof useMutation>;
  exportHint: string;
  navigate: ReturnType<typeof useNavigate>;
  activeDim: string | null;
  setActiveDim: (d: string | null) => void;
  detailTab: string;
  setDetailTab: (t: string) => void;
  reportMd: string | null;
  attribution: Parameters<typeof AttributionPanel>[0]["attribution"];
  citations: Citation[];
  onReset: () => void;
}) {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      {/* 顶部操作栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <PageHeader
            title="研判结果"
            description={`${displayName} 的风险分析已完成，可下钻明细或导出报告。`}
            compact
          />
        </div>
        <Button variant="outline" size="sm" onClick={onReset}>
          ← 新建分析
        </Button>
      </div>

      {/* 结果主区域 */}
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          {/* 左卡：核心结论 */}
          <Card>
            <CardContent className="space-y-4 pt-5">
              <GradeBadge grade={result.summary.grade} />
              <h2 className="text-2xl font-bold tracking-tight">{displayName}</h2>
              <p className="text-base leading-relaxed text-foreground">
                <LinkedText text={result.summary.headline} citations={citations} />
              </p>
              {result.summary.headline_meta?.polished ? (
                <p className="rounded bg-primary/[0.04] px-2.5 py-1.5 text-xs text-muted-foreground">
                  结论句经 AI 润色 \u00B7 Number Gate 已通过
                </p>
              ) : null}
              <p className="text-sm text-muted-foreground">
                综合危险度 {result.summary.score} \u00B7 指标 {result.metrics_count ?? "\u2014"} \u00B7 冲突{" "}
                {result.risk.quality.conflicts}
                <span className="ml-2 text-[11px] opacity-70">（蓝链为溯源，悬停查看出处）</span>
              </p>

              {/* 行动按钮组 */}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={!targetId || report.isPending}
                  onClick={() =>
                    report.mutate({ id: targetId!, confirm: false, template: "risk_onepager" })
                  }
                >
                  <FileText size={14} /> 一页摘要
                </Button>
                <Button
                  type="button"
                  size="sm"
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
                  size="sm"
                  variant="outline"
                  disabled={!targetId || report.isPending}
                  onClick={() =>
                    report.mutate({ id: targetId!, confirm: true, template: "credit_assessment" })
                  }
                >
                  信用报告 Word/PDF
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={!targetId}
                  onClick={() => navigate("/investigation")}
                >
                  <Network size={14} /> 进入调查
                </Button>
              </div>
              {exportHint ? <p className="text-xs text-muted-foreground">{exportHint}</p> : null}
            </CardContent>
          </Card>

          {/* 右卡：五维雷达 */}
          <Card>
            <CardHeader>
              <CardTitle>五维风险雷达</CardTitle>
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

        {/* 明细下钻 */}
        <Card>
          <CardHeader>
            <CardTitle>明细下钻</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs value={detailTab} onValueChange={setDetailTab}>
              <TabsList className="flex h-auto flex-wrap justify-start">
                <TabsTrigger value="attribution">归因分析</TabsTrigger>
                <TabsTrigger value="conflicts">多源冲突</TabsTrigger>
                <TabsTrigger value="industry">行业对标</TabsTrigger>
                <TabsTrigger value="stress">压力测试</TabsTrigger>
                <TabsTrigger value="graph">担保图谱</TabsTrigger>
                {reportMd ? <TabsTrigger value="report">报告预览</TabsTrigger> : null}
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
                  <p className="text-sm text-muted-foreground">当前数据暂无担保图谱</p>
                )}
              </TabsContent>
              {reportMd ? (
                <TabsContent value="report">
                  <div className="space-y-1 rounded-lg bg-muted/40 p-4 text-sm leading-relaxed">
                    {reportMd.split("\n").map((line, i) => (
                      <p
                        key={i}
                        className={cn(line.startsWith("#") ? "font-semibold text-foreground" : "")}
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
    </main>
  );
}