import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export function StatusChip({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "bad";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "border-border bg-secondary/70 text-muted-foreground",
        tone === "ok" && "border-[hsl(var(--grade-green)/0.28)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green",
        tone === "bad" && "border-destructive/25 bg-destructive/10 text-destructive",
        className,
      )}
    >
      {children}
    </span>
  );
}
