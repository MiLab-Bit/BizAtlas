import { FileText, Search } from "lucide-react";
import type { EvidenceItem } from "@/shared/lib/api";
import { StatusChip } from "@/shared/ui";

export function EvidencePanel({ evidence }: { evidence: EvidenceItem[] }) {
  if (!evidence.length) {
    return <p className="text-sm text-muted-foreground">暂无证据</p>;
  }
  return (
    <ul className="space-y-2">
      {evidence.map((ev) => (
        <li key={ev.id} className="rounded-lg border border-border bg-card/70 p-2.5">
          <div className="flex items-center gap-2">
            {ev.kind === "rag" ? (
              <Search size={13} className="shrink-0 text-primary" />
            ) : (
              <FileText size={13} className="shrink-0 text-muted-foreground" />
            )}
            <span className="truncate text-xs font-medium text-foreground">
              {ev.label || ev.source}
            </span>
            {ev.dimension ? <StatusChip tone="neutral">{ev.dimension}</StatusChip> : null}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
            {ev.kind === "rag" && ev.confidence != null ? (
              <span>置信度 {Math.round(ev.confidence * 100)}%</span>
            ) : null}
            {ev.tier ? <span>来源层 {ev.tier}</span> : null}
            {ev.page != null ? <span>第 {ev.page} 页</span> : null}
            {ev.value != null ? <span>值 {ev.value}</span> : null}
          </div>
          {ev.source ? (
            <p className="mt-0.5 truncate text-[10px] text-muted-foreground/70">
              来源：{ev.source}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
