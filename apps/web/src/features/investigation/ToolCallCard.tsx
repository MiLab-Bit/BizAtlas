import type { ToolCall } from "@/shared/lib/api";
import { StatusChip } from "@/shared/ui";
import { cn } from "@/shared/lib/cn";

const KIND_LABEL: Record<string, string> = {
  rule: "规则",
  compute: "计算",
  rag: "检索",
  template: "模板",
};

export function ToolCallCard({ call }: { call: ToolCall }) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card/70 p-2.5",
        !call.ok && "border-destructive/30",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs text-foreground">{call.name}</span>
          <StatusChip tone="neutral">{KIND_LABEL[call.kind] ?? call.kind}</StatusChip>
        </div>
        <StatusChip tone={call.ok ? "ok" : "bad"}>{call.ok ? "成功" : "缺口"}</StatusChip>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {call.agent_label} · {call.detail}
      </p>
      <p className="mt-0.5 text-[11px] font-medium text-foreground/80">→ {call.result}</p>
    </div>
  );
}
