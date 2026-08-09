import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  FileText,
  LayoutDashboard,
  LogOut,
  Network,
  Scale,
  Search,
  Shield,
  User as UserIcon,
  Database,
  Bot,
  ChevronDown,
} from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { fetchHealth } from "@/shared/lib/api";
import { fetchMe, getStoredUser, logout, type AuthUser } from "@/shared/lib/auth";
import { cn } from "@/shared/lib/cn";
import { StatusChip } from "@/shared/ui";

export function Shell() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(getStoredUser());

  // 数据源接入状态（来自 /v1/health 的 providers 列表）
  const [srcOpen, setSrcOpen] = useState(false);
  // 更多菜单（调查 / 工程能力）
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const srcRef = useRef<HTMLDivElement>(null);
  const providers = health.data?.providers ?? [];
  const enabledProviders = providers.filter((p) => p.enabled);
  const readyCount = enabledProviders.filter((p) => p.ok).length;
  const enabledCount = enabledProviders.length;
  const sourcesTone: "neutral" | "ok" | "bad" = !enabledCount
    ? "neutral"
    : enabledProviders.every((p) => p.ok)
    ? "ok"
    : "bad";

  // 点击外部关闭数据源下拉 / 更多菜单
  useEffect(() => {
    if (!srcOpen && !moreOpen) return;
    function onDown(e: MouseEvent) {
      if (srcRef.current && !srcRef.current.contains(e.target as Node)) setSrcOpen(false);
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [srcOpen, moreOpen]);

  // 挂载时校验令牌并刷新用户信息（令牌失效则清空本地态）
  useEffect(() => {
    let active = true;
    fetchMe().then((u) => {
      if (active) setUser(u);
    });
    return () => {
      active = false;
    };
  }, []);

  function handleLogout() {
    logout();
    setUser(null);
    navigate("/login");
  }

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

        <nav className="flex items-center gap-0.5">
          {(
            [
              ["/", "背调对话", Search, "输入企业名，AI 对话式背调", true],
              ["/workbench", "风险分析", LayoutDashboard, "上传资料，深度研判与报告", false],
              ["/reports", "报告记录", FileText, "历史分析沉淀与导出", false],
              ["/rules", "规则中心", Scale, "自定义风险规则", false],
            ] as const
          ).map(([to, label, Icon, hint, end]) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={hint}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-secondary text-foreground",
                )
              }
            >
              <Icon size={15} />
              <span className="hidden sm:inline">{label}</span>
            </NavLink>
          ))}
          {/* 更多：调查 / 工程能力 */}
          <div ref={moreRef} className="relative">
            <button
              type="button"
              onClick={() => setMoreOpen((o) => !o)}
              title="更多功能"
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                moreOpen && "bg-accent text-accent-foreground",
              )}
            >
              <ChevronDown size={15} className={cn("transition-transform", moreOpen && "rotate-180")} />
              <span className="hidden sm:inline">更多</span>
            </button>
            {moreOpen && (
              <div className="absolute right-0 top-full z-40 mt-1 w-56 rounded-lg border border-border bg-card p-1.5 shadow-lg">
                {([
                  ["/investigation", "Agent 调查", Network, "多 Agent 协作过程回放"],
                  ["/engineering", "工程能力", Bot, "Agent 编排与技术架构说明"],
                ] as const).map(([to, label, Icon, desc]) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMoreOpen(false)}
                    className="flex items-start gap-2.5 rounded-md px-3 py-2.5 text-sm transition-colors hover:bg-muted"
                  >
                    <Icon size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                    <div>
                      <div className="font-medium text-foreground">{label}</div>
                      <div className="text-[11px] leading-snug text-muted-foreground">{desc}</div>
                    </div>
                  </NavLink>
                ))}
              </div>
            )}
          </div>
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
          {/* 数据源接入状态 */}
          {providers.length ? (
            <div ref={srcRef} className="relative">
              <button
                type="button"
                onClick={() => setSrcOpen((o) => !o)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
                  sourcesTone === "neutral" && "border-border bg-secondary/70 text-muted-foreground",
                  sourcesTone === "ok" && "border-[hsl(var(--grade-green)/0.28)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green",
                  sourcesTone === "bad" && "border-destructive/25 bg-destructive/10 text-destructive",
                )}
              >
                <Database size={12} />
                数据源 {readyCount}/{enabledCount}
              </button>
              {srcOpen && (
                <div className="absolute right-0 top-full z-40 mt-2 w-72 rounded-lg border border-border bg-card p-2 shadow-lg">
                  <div className="px-1 pb-1.5 text-[0.7rem] font-medium uppercase tracking-wide text-muted-foreground">
                    数据源接入状态
                  </div>
                  <ul className="flex flex-col gap-0.5">
                    {providers.map((p) => {
                      const tone = !p.enabled ? "neutral" : p.ok ? "ok" : "bad";
                      return (
                        <li
                          key={p.id}
                          className="flex items-center justify-between gap-2 rounded-md px-1 py-1 text-sm hover:bg-accent"
                          title={p.message || undefined}
                        >
                          <span className="truncate text-foreground">{p.name}</span>
                          <span
                            className={cn(
                              "shrink-0 rounded-full border px-1.5 py-0.5 text-[0.65rem] font-medium",
                              tone === "neutral" && "border-border bg-secondary/70 text-muted-foreground",
                              tone === "ok" && "border-[hsl(var(--grade-green)/0.28)] bg-[hsl(var(--grade-green)/0.1)] text-grade-green",
                              tone === "bad" && "border-destructive/25 bg-destructive/10 text-destructive",
                            )}
                          >
                            {!p.enabled ? "未启用" : p.ok ? "就绪" : "异常"}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          ) : null}

          {user ? (
            <div className="flex items-center gap-1.5">
              <StatusChip tone="ok">
                <UserIcon size={12} />
                {user.nickname || user.email}
                <span className="opacity-60">·{user.role}</span>
              </StatusChip>
              <button
                type="button"
                onClick={handleLogout}
                title="退出登录"
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <LogOut size={13} />
                退出
              </button>
            </div>
          ) : (
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <UserIcon size={15} />
              登录
            </Link>
          )}
        </div>
      </header>
      <Outlet />
    </div>
  );
}
