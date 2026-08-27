import { AlertTriangle } from "lucide-react";
import type { TraceEvent } from "@/shared/lib/api";
import { cn } from "@/shared/lib/cn";

export function EventTimeline({
  events,
  cursor,
  onJump,
}: {
  events: TraceEvent[];
  cursor: number;
  onJump?: (seq: number) => void;
}) {
  if (!events.length) {
    return <p className="text-sm text-muted-foreground">暂无事件</p>;
  }
  return (
    <ol className="relative">
      {events.map((e) => {
        const shown = e.seq <= cursor;
        const isLast = e.seq === cursor;
        const isWarn = e.level === "warn";
        return (
          <li key={e.seq} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "mt-1 grid h-3 w-3 place-items-center rounded-full border",
                  shown
                    ? isWarn
                      ? "border-destructive bg-destructive/20"
                      : "border-primary bg-primary/20"
                    : "border-border bg-muted",
                )}
              />
              {e.seq < events.length - 1 && (
                <span className={cn("w-px flex-1", shown ? "bg-primary/30" : "bg-border")} />
              )}
            </div>
            <button
              type="button"
              disabled={!shown}
              onClick={() => onJump?.(e.seq)}
              className={cn("flex-1 pb-3 text-left", !shown && "opacity-40")}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-muted-foreground">
                  {(e.ts_offset_ms / 1000).toFixed(2)}s
                </span>
                <span className="text-[11px] font-medium text-foreground/70">
                  {e.agent_label}
                </span>
                {isWarn && <AlertTriangle size={12} className="text-destructive" />}
                {isLast && (
                  <span className="animate-pulse rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                    进行中
                  </span>
                )}
              </div>
              <p
                className={cn(
                  "text-xs",
                  isWarn ? "text-destructive/90" : "text-foreground",
                )}
              >
                {e.message}
              </p>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
