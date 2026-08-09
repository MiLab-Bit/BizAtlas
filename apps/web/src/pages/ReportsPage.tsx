import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  FileText,
  Download,
  Clock,
  Inbox,
  FileDown,
} from "lucide-react";
import {
  createReport,
  fetchFixtures,
  fetchReportMarkdown,
  fetchReportsList,
} from "@/shared/lib/api";
import { useUiStore } from "@/shared/store/ui";
import { cn } from "@/shared/lib/cn";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  GradeBadge,
  NativeSelect,
  PageHeader,
} from "@/shared/ui";

function fmtTime(iso?: string | null) {
  if (!iso) return "";
  return iso.replace("T", " ").slice(0, 16);
}

export function ReportsPage() {
  const { selectedFixture, setSelectedFixture } = useUiStore();
  const fixtures = useQuery({ queryKey: ["fixtures"], queryFn: fetchFixtures });
  const list = useQuery({ queryKey: ["reports-list"], queryFn: fetchReportsList });
  const [preview, setPreview] = useState("");
  const [activeTitle, setActiveTitle] = useState("");
  const [hint, setHint] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);

  const report = useMutation({
    mutationFn: (args: {
      confirm: boolean;
      template: "risk_onepager" | "credit_assessment";
    }) => createReport(selectedFixture, args.confirm, args.template),
    onSuccess: (data) => {
      if (data.markdown) {
        setPreview(data.markdown);
        setActiveTitle(data.analysis_title || "分析预览");
      }
      setHint(
        [
          data.analysis_title || "",
          data.status_label || "",
          data.pdf_path ? "已含 PDF" : "",
          data.docx_path ? "已含 Word" : "",
        ]
          .filter(Boolean)
          .join(" \u00B7 "),
      );
      void list.refetch();
    },
  });

  async function openHistory(id: string, title: string) {
    setActiveId(id);
    setActiveTitle(title);
    try {
      const md = await fetchReportMarkdown(id);
      setPreview(md);
    } catch (err) {
      setPreview(err instanceof Error ? err.message : String(err));
    }
  }

  const hasHistory = (list.data?.length ?? 0) > 0;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      <PageHeader
        title="报告与记录"
        description="所有历史研判报告的沉淀中心。可在此查看、预览，或导出为 Word / PDF 文件。"
        compact
        actions={
          <>
            <NativeSelect
              value={selectedFixture}
              onChange={(e) => setSelectedFixture(e.target.value)}
              className="max-w-[180px]"
            >
              {(fixtures.data ?? ["healthy", "risky", "defaulted"]).map((id) => (
                <option key={id} value={id}>
                  {id === "healthy"
                    ? "healthy \u00B7 健康"
                    : id === "risky"
                      ? "risky \u00B7 风险"
                      : "defaulted \u00B7 违约"}
                </option>
              ))}
            </NativeSelect>
            <Button
              type="button"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: false, template: "risk_onepager" })}
            >
              <FileText size={14} /> 生成摘要
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: true, template: "risk_onepager" })}
            >
              <Download size={14} /> 导出摘要
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: true, template: "credit_assessment" })}
            >
              <FileDown size={14} /> 信用报告
            </Button>
          </>
        }
      >
        {hint ? (
          <div className="rounded bg-primary/[0.04] px-3 py-1.5 text-sm text-muted-foreground">
            {hint}
          </div>
        ) : null}
      </PageHeader>

      {/* 无历史时的引导 */}
      {!hasHistory && !preview && (
        <section className="flex flex-col items-center rounded-2xl border border-dashed border-border bg-card/50 px-6 py-14 text-center animate-rise">
          <Inbox size={32} className="mb-3 text-muted-foreground/50" strokeWidth={1.5} />
          <p className="text-base font-semibold text-foreground">暂无历史记录</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            在「背调对话」中开始调研，或在「风险分析」中完成研判后，报告会自动沉淀到这里。
            也可以直接使用上方按钮为演示案例生成报告。
          </p>
          <div className="mt-4 flex gap-2">
            <Button size="sm" variant="outline" asChild>
              <a href="/">去背调对话 →</a>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <a href="/workbench">去风险分析 →</a>
            </Button>
          </div>
        </section>
      )}

      {/* 历史列表 + 预览 */}
      {(hasHistory || preview) && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          {/* 左：历史记录 */}
          <Card>
            <CardHeader className="flex-row items-center gap-2 pb-3">
              <Clock size={16} className="text-muted-foreground" />
              <CardTitle className="text-base">历史记录</CardTitle>
              <span className="ml-auto text-xs text-muted-foreground">{list.data?.length ?? 0} 条</span>
            </CardHeader>
            <CardContent className="space-y-1 p-3">
              {!hasHistory ? (
                <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                  生成报告后会出现在此
                </p>
              ) : (
                (list.data ?? []).map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => openHistory(r.id, r.title)}
                    className={cn(
                      "flex w-full flex-col gap-1.5 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted",
                      activeId === r.id && "bg-muted ring-1 ring-primary/20",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-foreground">{r.title}</span>
                      {r.grade ? <GradeBadge grade={r.grade} size="sm" /> : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <span>{r.kind || "风险分析"}</span>
                      <span className="opacity-40">\u00B7</span>
                      <span>{r.status_label || "已生成"}</span>
                      <span className="opacity-40">\u00B7</span>
                      <span>{fmtTime(r.created_at)}</span>
                    </div>
                    {r.headline ? (
                      <span className="line-clamp-2 text-xs leading-relaxed text-muted-foreground/80">
                        {r.headline}
                      </span>
                    ) : null}
                  </button>
                ))
              )}
            </CardContent>
          </Card>

          {/* 右：内容预览 */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{activeTitle || "报告预览"}</CardTitle>
            </CardHeader>
            <CardContent>
              {preview ? (
                <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-4 font-mono text-xs leading-relaxed text-foreground">
                  {preview}
                </pre>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <FileText size={28} className="mb-2 text-muted-foreground/40" strokeWidth={1.5} />
                  <p className="text-sm text-muted-foreground">
                    点击左侧一条记录查看报告内容，<br />或用上方按钮生成新报告
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </main>
  );
}