import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Building2, Send, Sparkles, FileText, BarChart3, MessageSquareText, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { postBackgroundChat, startBackgroundCheck } from "@/shared/lib/api";
import { Button, GradeBadge, Input, StatusChip } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";

type Turn = { role: "user" | "assistant"; content: string; meta?: string };

/** 常用示例企业，点击即可快速开始 */
const QUICK_EXAMPLES = [
  { name: "腾讯", label: "互联网巨头" },
  { name: "某建材公司", label: "演示案例" },
  { name: "阿里巴巴", label: "电商平台" },
];

/** 聊天阶段建议问题 */
const SUGGESTED_QUESTIONS = [
  "这家公司主要风险是什么？",
  "工商登记和失信情况如何？",
  "股权结构和实际控制人？",
  "还需要核验哪些信息？",
];

function friendlyError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (/not found/i.test(raw) || raw.includes("404")) {
    return "背调服务未连接，请确认后端 API 已启动后重试。";
  }
  if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(raw)) {
    return "无法连接后端，请确认 BizAtlas API 已启动。";
  }
  return raw;
}

export function IntakePage() {
  const [name, setName] = useState("");
  const [session, setSession] = useState<{
    companyId: string;
    companyName: string;
    fixtureId?: string | null;
    grade?: string | null;
    score?: number | null;
  } | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");

  const start = useMutation({
    mutationFn: () => startBackgroundCheck(name.trim()),
    onSuccess: (data) => {
      setError("");
      const summary = data.summary as { grade?: string; score?: number } | null | undefined;
      setSession({
        companyId: data.company_id,
        companyName: data.company_name,
        fixtureId: data.fixture_id,
        grade: summary?.grade ?? null,
        score: summary?.score ?? null,
      });
      const tyc = data.tianyancha as { ok?: boolean; configured?: boolean } | undefined;
      setTurns([
        {
          role: "assistant",
          content: data.message || `已开始对「${data.company_name}」背调，请继续提问。`,
          meta: [
            data.llm_used ? "LLM" : null,
            tyc?.ok ? "天眼查" : tyc?.configured ? "天眼查未命中" : null,
          ]
            .filter(Boolean)
            .join(" · "),
        },
      ]);
      setInput("");
    },
    onError: (err) => setError(friendlyError(err)),
  });

  const chat = useMutation({
    mutationFn: (message: string) => {
      if (!session) throw new Error("请先输入企业名称并开始背调");
      const history = turns.map((t) => ({ role: t.role, content: t.content }));
      return postBackgroundChat({
        companyName: session.companyName,
        companyId: session.companyId,
        fixtureId: session.fixtureId,
        message,
        history,
      });
    },
    onSuccess: (data, message) => {
      const facts = data.facts as { grade?: string; score?: number } | undefined;
      if (facts?.grade || facts?.score != null) {
        setSession((s) =>
          s
            ? {
                ...s,
                grade: (facts.grade as string) || s.grade,
                score: typeof facts.score === "number" ? facts.score : s.score,
              }
            : s,
        );
      }
      setTurns((prev) => [
        ...prev,
        { role: "user", content: message },
        {
          role: "assistant",
          content: data.answer,
          meta: [data.llm_used ? "LLM" : null, data.facts?.tianyancha_ok ? "天眼查" : null]
            .filter(Boolean)
            .join(" · "),
        },
      ]);
    },
    onError: (err) => setError(friendlyError(err)),
  });

  function send(text: string) {
    const msg = text.trim();
    if (!msg || chat.isPending) return;
    setInput("");
    setError("");
    chat.mutate(msg);
  }

  function pickExample(exampleName: string) {
    setName(exampleName);
    // 稍后自动触发，让用户看到名字被填入
    setTimeout(() => start.mutate(), 100);
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-8">
      {/* ====== 三步引导条 ====== */}
      <section className="flex items-center justify-center gap-0 overflow-hidden rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-sm">
        {[
          { icon: MessageSquareText, step: "1", label: "输入企业名", active: !session },
          { icon: Sparkles, step: "2", label: "对话背调", active: !!session },
          { icon: BarChart3, step: "3", label: "查看报告", active: false },
        ].map(({ icon: Icon, step, label, active }, idx) => (
          <div key={step} className="flex items-center">
            <div
              className={cn(
                "flex items-center gap-1.5 font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold",
                  active ? "bg-primary text-primary-foreground" : "bg-border text-muted-foreground",
                )}
              >
                {step}
              </span>
              <Icon size={14} />
              <span>{label}</span>
            </div>
            {idx < 2 && (
              <div className="mx-3 h-px w-8 bg-border/60" aria-hidden="true" />
            )}
          </div>
        ))}
      </section>

      {/* ====== Hero 区：输入企业名 / 会话状态 ====== */}
      <section className="relative overflow-hidden rounded-2xl border border-border/80 bg-card/90 px-6 py-10 shadow-[0_1px_0_hsl(var(--border)/0.6),0_12px_40px_-24px_hsl(var(--primary)/0.28)] animate-rise">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(720px_300px_at_100%_0%,hsl(var(--primary)/0.12),transparent_58%)]"
        />
        <div className="relative space-y-5">
          <p className="text-xs font-semibold tracking-[0.28em] text-primary">BizAtlas</p>

          {!session ? (
            <>
              <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">输入企业名，对话式背调</h1>
              <p className="max-w-xl text-base text-muted-foreground">
                写下目标企业名（全称或简称均可），用自然语言追问风险与信用要点。工商司法数据来自天眼查，分析由 LLM 整理。
              </p>

              <form
                className="flex flex-col gap-3 sm:flex-row sm:items-center"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (name.trim()) start.mutate();
                }}
              >
                <div className="relative flex-1">
                  <Building2
                    size={16}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                  />
                  <Input
                    className="h-11 pl-9"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：腾讯、阿里巴巴、某建材公司…"
                    autoFocus
                  />
                </div>
                <Button type="submit" size="lg" disabled={start.isPending || !name.trim()}>
                  {start.isPending ? "查询中…" : "开始背调"}
                  <ArrowRight size={16} />
                </Button>
              </form>

              {/* 快速示例 */}
              <div className="pt-1">
                <p className="mb-2 text-xs text-muted-foreground">试试示例：</p>
                <div className="flex flex-wrap gap-2">
                  {QUICK_EXAMPLES.map((ex) => (
                    <button
                      key={ex.name}
                      type="button"
                      onClick={() => pickExample(ex.name)}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary"
                    >
                      <Sparkles size={11} />
                      {ex.name}
                      <span className="opacity-50">{ex.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* 会话态头部 */}
              <div className="space-y-3">
                <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">正在背调</h1>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusChip tone="ok">{session.companyName}</StatusChip>
                  {session.grade ? <GradeBadge grade={session.grade} size="sm" /> : null}
                  {session.score != null ? <StatusChip>危险度 {session.score}</StatusChip> : null}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSession(null);
                      setTurns([]);
                      setError("");
                    }}
                  >
                    换一家
                  </Button>
                </div>
              </div>

              {/* 深入分析入口 */}
              <div className="rounded-lg border border-primary/20 bg-primary/[0.03] px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm">
                    <FileText size={15} className="text-primary" />
                    <span className="font-medium text-foreground">
                      想要五维雷达图、归因下钻、完整报告？
                    </span>
                  </div>
                  <Button type="button" size="sm" asChild>
                    <Link to="/workbench">进入风险分析 →</Link>
                  </Button>
                </div>
              </div>
            </>
          )}

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
      </section>

      {/* ====== 对话区 ====== */}
      {session ? (
        <section className="flex min-h-[420px] flex-col rounded-2xl border border-border/80 bg-card/80 shadow-sm animate-rise">
          <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-4">
            {turns.map((t, i) => (
              <div
                key={`${t.role}-${i}`}
                className={
                  t.role === "user"
                    ? "ml-8 rounded-xl bg-primary px-3.5 py-2.5 text-sm text-primary-foreground"
                    : "mr-6 rounded-xl bg-muted/70 px-3.5 py-2.5 text-sm text-foreground"
                }
              >
                <p className="whitespace-pre-wrap leading-relaxed">{t.content}</p>
                {t.meta ? <p className="mt-1 text-[10px] opacity-70">{t.meta}</p> : null}
              </div>
            ))}
            {chat.isPending ? (
              <div className="mr-6 rounded-xl bg-muted/70 px-3.5 py-2.5 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 animate-round rounded-full bg-primary" />
                  正在分析…
                </div>
              </div>
            ) : null}
          </div>

          {/* 建议问题 + 输入区 */}
          <div className="space-y-0">
            <div className="flex flex-wrap gap-1.5 border-t border-border/60 px-3 pt-2.5">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  onClick={() => send(q)}
                >
                  {q}
                </button>
              ))}
            </div>

            <form
              className="flex gap-2 border-t border-border/80 p-3"
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="继续追问任何问题…"
                className="flex-1"
              />
              <Button type="submit" size="icon" disabled={chat.isPending || !input.trim()}>
                <Send size={16} />
              </Button>
            </form>
          </div>
        </section>
      ) : null}

      {/* ====== 底部功能引导（无会话时显示）===== */}
      {!session ? (
        <section className="grid gap-3 sm:grid-cols-3">
          {[
            {
              icon: Upload,
              title: "上传资料研判",
              desc: "有财务报表或经营数据？上传 CSV/PDF 自动分析风险。",
              to: "/workbench",
              cta: "去上传",
            },
            {
              icon: Scale,
              title: "自定义规则",
              desc: "用自然语言描述风险规则，AI 编写并激活计分。",
              to: "/rules",
              cta: "写规则",
            },
            {
              icon: FileText,
              title: "历史报告",
              desc: "查看过往所有研判记录，导出 Word 或 PDF 报告。",
              to: "/reports",
              cta: "看记录",
            },
          ].map(({ icon: Icon, title, desc, to, cta }) => (
            <Link
              key={title}
              to={to}
              className="group flex flex-col gap-2 rounded-xl border border-border/60 bg-card/60 p-4 transition-colors hover:border-primary/25 hover:bg-card"
            >
              <Icon size={20} className="text-muted-foreground transition-colors group-hover:text-primary" />
              <div>
                <div className="text-sm font-semibold text-foreground">{title}</div>
                <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{desc}</div>
              </div>
              <span className="mt-auto inline-flex w-fit text-[11px] font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                {cta} →
              </span>
            </Link>
          ))}
        </section>
      ) : null}
    </main>
  );
}