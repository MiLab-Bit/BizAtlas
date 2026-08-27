import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  XCircle,
} from "lucide-react";
import type { AgentTrace } from "@/shared/lib/api";
import { StatusChip } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";

const STATUS_META: Record<
  string,
  { label: string; tone: "ok" | "bad" | "neutral"; Icon: LucideIcon }
> = {
  completed: { label: "已完成", tone: "ok", Icon: CheckCircle2 },
  running: { label: "运行中", tone: "neutral", Icon: Loader2 },
  failed: { label: "失败", tone: "bad", Icon: XCircle },
  blocked: { label: "已阻断", tone: "bad", Icon: AlertTriangle },
  waiting_review: { label: "待复核", tone: "neutral", Icon: CircleDashed },
  queued: { label: "排队中", tone: "neutral", Icon: CircleDashed },
};

const MODE_LABEL: Record<string, string> = {
  deterministic: "确定性",
  llm: "LLM 增强",
  fallback: "降级",
};

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-muted/40 py-1">
      <div className="text-sm font-semibold text-foreground">{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}

export function AgentCard({
  agent,
  active,
  onClick,
}: {
  agent: AgentTrace;
  active?: boolean;
  onClick?: () => void;
}) {
  const meta = STATUS_META[agent.status] ?? STATUS_META.queued!;
  const Icon = meta.Icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-xl border border-border bg-card p-3 text-left transition-colors hover:bg-accent/40",
        active && "ring-2 ring-primary/40",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon
            size={16}
            className={cn(
              agent.status === "running" && "animate-spin",
              meta.tone === "ok" && "text-grade-green",
              meta.tone === "bad" && "text-destructive",
              meta.tone === "neutral" && "text-muted-foreground",
            )}
          />
          <span className="truncate text-sm font-semibold text-foreground">
            {agent.label}
          </span>
        </div>
        <StatusChip tone={meta.tone}>{meta.label}</StatusChip>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{agent.task}</p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        <Stat label="输入" value={agent.inputs} />
        <Stat label="输出" value={agent.outputs} />
        <Stat label="证据" value={agent.evidence} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <StatusChip tone={agent.mode === "llm" ? "ok" : "neutral"}>
          {MODE_LABEL[agent.mode] ?? agent.mode}
        </StatusChip>
        {agent.tool_calls.map((t) => (
          <span
            key={t}
            className="rounded bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
          >
            {t}
          </span>
        ))}
      </div>
      {agent.notes?.map((n, i) => (
        <p key={i} className="mt-1.5 text-[11px] text-muted-foreground/80">
          · {n}
        </p>
      ))}
    </button>
  );
}
