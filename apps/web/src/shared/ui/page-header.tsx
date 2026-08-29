import type { ReactNode } from "react";
import { cn } from "@/shared/lib/cn";

export function PageHeader({
  brand = "BizAtlas",
  title,
  description,
  actions,
  children,
  className,
  compact,
}: {
  brand?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border/80 bg-card/90 px-6 py-8 shadow-[0_1px_0_hsl(var(--border)/0.6),0_12px_40px_-24px_hsl(var(--primary)/0.28)] animate-rise",
        compact ? "py-6" : "py-10",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(720px_300px_at_100%_0%,hsl(var(--primary)/0.1),transparent_58%),linear-gradient(135deg,hsl(var(--accent)/0.55)_0%,transparent_42%)]"
      />
      <div className="relative space-y-4">
        <p className="text-xs font-semibold tracking-[0.28em] text-primary">{brand}</p>
        <div className="max-w-2xl space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">{title}</h1>
          {description ? <p className="max-w-xl text-base leading-relaxed text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        {children}
      </div>
    </section>
  );
}
