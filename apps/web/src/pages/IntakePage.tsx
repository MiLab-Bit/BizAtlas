import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Building2, Send } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { postBackgroundChat, startBackgroundCheck } from "@/shared/lib/api";
import { Button, GradeBadge, Input, StatusChip } from "@/shared/ui";

type Turn = { role: "user" | "assistant"; content: string; meta?: string };

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

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-10">
      <section className="relative overflow-hidden rounded-2xl border border-border/80 bg-card/90 px-6 py-10 shadow-[0_1px_0_hsl(var(--border)/0.6),0_12px_40px_-24px_hsl(var(--primary)/0.28)] animate-rise">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(720px_300px_at_100%_0%,hsl(var(--primary)/0.12),transparent_58%)]"
        />
        <div className="relative space-y-5">
          <p className="text-xs font-semibold tracking-[0.28em] text-primary">BizAtlas</p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">输入企业名，对话背调</h1>
          <p className="max-w-xl text-base text-muted-foreground">
            写下目标企业，用自然语言追问风险与信用要点。工商司法走天眼查，叙述由 LLM 整理，关键数字仍受 Number Gate 约束。
          </p>

          {!session ? (
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
                  placeholder="输入企业全称或简称"
                  autoFocus
                />
              </div>
              <Button type="submit" size="lg" disabled={start.isPending || !name.trim()}>
                {start.isPending ? "查询中…" : "开始背调"}
                <ArrowRight size={16} />
              </Button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip tone="ok">{session.companyName}</StatusChip>
              {session.grade ? <GradeBadge grade={session.grade} size="sm" /> : null}
              {session.score != null ? (
                <StatusChip>危险度 {session.score}</StatusChip>
              ) : null}
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
              <Button type="button" variant="ghost" size="sm" asChild>
                <Link to="/workbench">进工作台</Link>
              </Button>
            </div>
          )}

          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </div>
      </section>

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
            {chat.isPending ? <p className="text-xs text-muted-foreground">背调中…</p> : null}
          </div>

          <div className="flex flex-wrap gap-1.5 border-t border-border/60 px-3 py-2">
            {["主要风险是什么？", "工商与失信情况？", "还要核验什么？"].map((q) => (
              <button
                key={q}
                type="button"
                className="rounded-md border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted"
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
              placeholder="继续追问…"
              className="flex-1"
            />
            <Button type="submit" size="icon" disabled={chat.isPending || !input.trim()}>
              <Send size={16} />
            </Button>
          </form>
        </section>
      ) : null}
    </main>
  );
}
