import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
          .join(" · "),
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

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-5 py-6">
      <PageHeader
        title="报告中心"
        description="查看历史分析；导出需确认，数字来自计算管线。"
        compact
        actions={
          <>
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
            <Button
              type="button"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: false, template: "risk_onepager" })}
            >
              生成风险摘要
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: true, template: "risk_onepager" })}
            >
              导出摘要 Word/PDF
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={report.isPending}
              onClick={() => report.mutate({ confirm: true, template: "credit_assessment" })}
            >
              导出信用背调 Word/PDF
            </Button>
          </>
        }
      >
        {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader>
            <CardTitle>历史分析</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 p-3">
            {(list.data ?? []).length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                暂无历史分析，生成后会出现在此
              </p>
            ) : (
              (list.data ?? []).map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => openHistory(r.id, r.title)}
                  className={cn(
                    "flex w-full flex-col gap-1 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted",
                    activeId === r.id && "bg-muted",
                  )}
                >
                  <span className="text-sm font-medium text-foreground">{r.title}</span>
                  <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    {r.grade ? <GradeBadge grade={r.grade} size="sm" /> : null}
                    {r.kind || ""} · {r.status_label || "已生成"} · {fmtTime(r.created_at)}
                  </span>
                  {r.headline ? (
                    <span className="line-clamp-2 text-xs text-muted-foreground">{r.headline}</span>
                  ) : null}
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{activeTitle || "分析内容"}</CardTitle>
          </CardHeader>
          <CardContent>
            {preview ? (
              <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg bg-muted/40 p-4 font-mono text-xs leading-relaxed text-foreground">
                {preview}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">
                点击左侧历史分析查看内容，或上方生成新分析
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
