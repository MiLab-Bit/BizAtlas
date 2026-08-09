import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  FileText,
  LayoutDashboard,
  Network,
  Scale,
  Search,
  Shield,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { fetchHealth } from "@/shared/lib/api";
import { cn } from "@/shared/lib/cn";
import { StatusChip } from "@/shared/ui";

export function Shell() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-border/80 bg-card/80 px-5 py-3 backdrop-blur-md">
        <div className="flex min-w-[10rem] items-center gap-3">
          <div
            aria-hidden
            className="grid h-8 w-8 place-items-center rounded-lg bg-[linear-gradient(145deg,hsl(var(--primary))_0%,hsl(200_45%_32%)_100%)] text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.18)]"
          >
            <Shield size={16} strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-lg font-bold tracking-tight text-foreground">BizAtlas</div>
            <div className="text-[0.72rem] text-muted-foreground">企业经营与风险研判</div>
          </div>
        </div>

        <nav className="flex items-center gap-1">
          {(
            [
              ["/", "背调", Search, true],
              ["/workbench", "工作台", LayoutDashboard, false],
              ["/investigation", "调查", Network, false],
              ["/rules", "规则中心", Scale, false],
              ["/reports", "报告中心", FileText, false],
            ] as const
          ).map(([to, label, Icon, end]) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-secondary text-foreground",
                )
              }
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <StatusChip>
            <Activity size={12} />
            {health.data?.mode ?? "…"}
          </StatusChip>
          <StatusChip>rules {health.data?.rules_loaded ?? "—"}</StatusChip>
          <StatusChip tone={health.data?.llm_configured ? "ok" : "neutral"}>
            {health.data?.llm_configured
              ? `LLM ${health.data.llm_model || "OK"}`
              : "LLM off"}
          </StatusChip>
          <StatusChip
            tone={health.isError ? "bad" : health.data?.db_ok ? "ok" : "neutral"}
          >
            {health.isError ? "API OFF" : health.data?.db_ok ? "DB OK" : "DB …"}
          </StatusChip>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
