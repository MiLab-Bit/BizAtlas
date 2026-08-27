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
  KeyRound,
} from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { fetchHealth } from "@/shared/lib/api";
import { fetchMe, getStoredUser, logout, type AuthUser } from "@/shared/lib/auth";
import { cn } from "@/shared/lib/cn";
import { StatusChip } from "@/shared/ui";

const NAV = [
  ["/", "背调工作台", Search, "输入企业名，AI 对话式背调", true],
  ["/workbench", "风险分析", LayoutDashboard, "上传资料，深度研判与报告", false],
  ["/reports", "调查报告", FileText, "历史分析沉淀与导出", false],
  ["/rules", "规则中心", Scale, "自定义风险规则", false],
  ["/investigation", "Agent 调查", Network, "多 Agent 协作过程回放", false],
  ["/engineering", "工程能力", Bot, "Agent 编排与技术架构说明", false],
  ["/model-config", "模型配置", KeyRound, "配置你自己的大模型供应商密钥", false],
] as const;

export function Shell() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(getStoredUser());
  const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "true";

  // 数据源接入状态（来自 /v1/health 的 providers 列表）
  const [srcOpen, setSrcOpen] = useState(false);
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

  // 点击外部关闭数据源下拉
  useEffect(() => {
    if (!srcOpen) return;
    function onDown(e: MouseEvent) {
      if (srcRef.current && !srcRef.current.contains(e.target as Node)) setSrcOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [srcOpen]);

  // 挂载时校验令牌并刷新用户信息（令牌失效则清空本地态）
  useEffect(() => {
    let active = true;
    if (AUTH_DISABLED) return;
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
    <div className="flex h-screen overflow-hidden bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card/60">
        <div className="flex items-center gap-2.5 px-4 py-4">
          <div
            aria-hidden
            className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.18)]"
          >
            <Shield size={16} strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-base font-bold tracking-tight text-foreground">BizAtlas</div>
            <div className="text-[0.7rem] text-muted-foreground">企业经营与风险研判</div>
          </div>
        </div>

        <nav className="flex flex-col gap-0.5 px-2 py-2">
          {NAV.map(([to, label, Icon, hint, end]) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={hint}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon size={16} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto flex flex-col gap-2 border-t border-border px-3 py-3">
          <div className="flex flex-wrap items-center gap-1.5">
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
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
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
                  <div className="absolute bottom-full left-0 z-40 mb-2 w-72 rounded-lg border border-border bg-card p-2 shadow-lg">
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
          </div>
          <div className="flex items-center gap-1.5">
            {AUTH_DISABLED ? (<span className="text-xs text-muted-foreground">demo</span>) : user ? (
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
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
