import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  Cpu,
  Database,
  GitBranch,
  Layers,
  Network,
  ShieldCheck,
  Sparkles,
  Boxes,
  FileSearch,
  PenLine,
  Gauge,
  Workflow,
} from "lucide-react";
import { fetchHealth } from "@/shared/lib/api";
import { cn } from "@/shared/lib/cn";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  PageHeader,
  StatusChip,
} from "@/shared/ui";

type AgentInfo = {
  role_key: string;
  label: string;
  task: string;
  principle: string;
  icon: typeof Bot;
};

// 与后端 multi-agent pipeline 对齐（详见 InvestigationPage 的 seedAgents）
const AGENTS: AgentInfo[] = [
  {
    role_key: "classifier",
    label: "分类 Agent",
    task: "识别行业赛道 + 路由重点核查维度",
    principle: "先理解企业属于哪一类，再决定该重点查什么，避免无差别扫描。",
    icon: FileSearch,
  },
  {
    role_key: "planner",
    label: "规划 Agent",
    task: "枚举数据缺口 + 生成本地检索计划（失败感知）",
    principle: "在执行前显式列出缺什么、去哪查；检索失败会被感知而非被忽略。",
    icon: Workflow,
  },
  {
    role_key: "researcher",
    label: "研究 Agent",
    task: "本地 RAG 检索补充证据（缺则显式披露，绝不编造）",
    principle: "只基于真实证据；检索不到的部分会被标注为缺失，而不是编造填充。",
    icon: Boxes,
  },
  {
    role_key: "writer",
    label: "写作 Agent",
    task: "writer-only 叙事合成 + 披露透传（不改分）",
    principle: "叙事与评分职责分离——写作 Agent 无权改动风险评分，结论不被文风带偏。",
    icon: PenLine,
  },
  {
    role_key: "scoring",
    label: "风险评分内核",
    task: "规则匹配 + 五维加权评分 + 图谱 / 压力计算",
    principle: "确定性的评分核心，所有维度加权可追溯，是唯一有权给出分数的模块。",
    icon: Gauge,
  },
];

const STACK: { label: string; detail: string; icon: typeof Bot }[] = [
  { label: "后端", detail: "Python · FastAPI，zod 校验的响应信封，默认 SQLite（可接 Postgres）", icon: Cpu },
  { label: "前端", detail: "React 19 · TypeScript · Vite，类型安全与按需构建", icon: Layers },
  { label: "编排", detail: "多智能体（agents / orchestrator），确定性内核 + 可选 LLM 增强", icon: Network },
  { label: "数据", detail: "天眼查等外部数据源经 provider 适配，状态可观测、失败可降级", icon: Database },
];

const PRINCIPLES: { title: string; body: string }[] = [
  {
    title: "证据可溯源",
    body: "每一项结论都对应可追溯的证据条目；无证据支撑的判断不会被纳入评分。",
  },
  {
    title: "缺失显式披露，绝不编造",
    body: "检索覆盖不到的数据缺口会被显式标注，而非用模型生成内容填补。",
  },
  {
    title: "评分与叙事分离",
    body: "写作 Agent 为 writer-only，无权改动风险评分，避免文风影响结论。",
  },
  {
    title: "失败感知与降级",
    body: "当 LLM 或数据源不可用时，系统安全降级到确定性规则，而非整体失败。",
  },
];

export function EngineeringPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const data = health.data;
  const providers = data?.providers ?? [];
  const enabled = providers.filter((p) => p.enabled);
  const ready = enabled.filter((p) => p.ok).length;

  // 健康查询的三态：加载中 / 失败 / 就绪，避免干巴巴显示「—」
  const probe = (v: string | number | undefined): string =>
    health.isError ? "API 离线" : !data ? "连接中…" : (v ?? "—");

  return (
    <main className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 px-5 py-6">
      <PageHeader
        title="工程能力"
        description="了解 BizAtlas 的多智能体编排、运行时管线与工程原则——系统如何在「绝不编造」的约束下完成企业风险研判。"
        actions={
          <StatusChip tone={health.isError ? "bad" : data?.db_ok ? "ok" : "neutral"}>
            <ShieldCheck size={12} />
            {health.isError ? "后端离线" : data?.db_ok ? "后端就绪" : "连接中…"}
          </StatusChip>
        }
      />

      {/* 实时能力状态 */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs text-muted-foreground">服务版本</p>
            <p className="truncate text-lg font-semibold text-foreground">{probe(data?.version)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs text-muted-foreground">运行模式</p>
            <p className="truncate text-lg font-semibold text-foreground">{probe(data?.mode)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs text-muted-foreground">已载规则</p>
            <p className="text-lg font-semibold text-foreground">{probe(data?.rules_loaded)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 py-4">
            <p className="text-xs text-muted-foreground">LLM</p>
            <p className="truncate text-lg font-semibold text-foreground">
              {health.isError ? "API 离线" : !data ? "连接中…" : data.llm_configured ? (data.llm_model || "已配置") : "未启用"}
            </p>
          </CardContent>
        </Card>
      </section>

      {/* 技术栈 */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-primary" />
          <h2 className="text-lg font-bold tracking-tight text-foreground">技术栈</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {STACK.map((s) => (
            <Card key={s.label}>
              <CardContent className="flex items-start gap-3 py-4">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  <s.icon size={18} />
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">{s.label}</p>
                  <p className="text-sm leading-snug text-muted-foreground">{s.detail}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 多 Agent 编排 */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Network size={16} className="text-primary" />
          <h2 className="text-lg font-bold tracking-tight text-foreground">多 Agent 编排</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {AGENTS.map((a) => (
            <Card key={a.role_key}>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-secondary text-foreground">
                    <a.icon size={16} />
                  </div>
                  <CardTitle className="text-base">{a.label}</CardTitle>
                </div>
                <CardDescription className="pt-1 text-sm">{a.task}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-xs leading-snug text-muted-foreground">{a.principle}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 运行时管线模式 */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <GitBranch size={16} className="text-primary" />
          <h2 className="text-lg font-bold tracking-tight text-foreground">运行时管线</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Card className="border-border/80">
            <CardContent className="space-y-1 py-4">
              <p className="font-semibold text-foreground">确定性</p>
              <p className="text-sm text-muted-foreground">纯规则路径，零幻觉，始终可用。</p>
            </CardContent>
          </Card>
          <Card className="border-border/80">
            <CardContent className="space-y-1 py-4">
              <p className="font-semibold text-foreground">LLM 增强</p>
              <p className="text-sm text-muted-foreground">在确定性内核之上增强检索与叙事合成。</p>
            </CardContent>
          </Card>
          <Card className="border-border/80">
            <CardContent className="space-y-1 py-4">
              <p className="font-semibold text-foreground">降级</p>
              <p className="text-sm text-muted-foreground">能力不可用时安全回落，不整体失败。</p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* 数据源接入状态（实时） */}
      {providers.length ? (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Database size={16} className="text-primary" />
              <h2 className="text-lg font-bold tracking-tight text-foreground">数据源接入</h2>
            </div>
            <StatusChip tone={enabled.length && ready === enabled.length ? "ok" : "neutral"}>
              {ready}/{enabled.length} 就绪
            </StatusChip>
          </div>
          <Card>
            <CardContent className="space-y-1 py-2">
              {providers.map((p) => {
                const tone = !p.enabled ? "neutral" : p.ok ? "ok" : "bad";
                return (
                  <div
                    key={p.id}
                    className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-accent"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{p.name}</p>
                      {p.message ? (
                        <p className="truncate text-xs text-muted-foreground">{p.message}</p>
                      ) : null}
                    </div>
                    <StatusChip tone={tone}>
                      {!p.enabled ? "未启用" : p.ok ? "就绪" : "异常"}
                    </StatusChip>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </section>
      ) : null}

      {/* 工程原则 */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className="text-primary" />
          <h2 className="text-lg font-bold tracking-tight text-foreground">工程原则</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {PRINCIPLES.map((p) => (
            <Card key={p.title} className="border-border/80">
              <CardContent className="space-y-1 py-4">
                <p className="font-semibold text-foreground">{p.title}</p>
                <p className="text-sm leading-snug text-muted-foreground">{p.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <p className={cn("pb-4 text-center text-xs text-muted-foreground")}>
        BizAtlas · 企业经营与风险研判 · 多智能体编排，证据可溯源
      </p>
    </main>
  );
}
