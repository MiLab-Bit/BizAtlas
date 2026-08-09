import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Network, Pause, Play, RotateCcw } from "lucide-react";
import { postAnalyzePipeline } from "@/shared/lib/api";
import { useUiStore } from "@/shared/store/ui";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  GradeBadge,
  StatusChip,
} from "@/shared/ui";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { AgentCard } from "@/features/investigation/AgentCard";
import { ToolCallCard } from "@/features/investigation/ToolCallCard";
import { EventTimeline } from "@/features/investigation/EventTimeline";
import { EvidencePanel } from "@/features/investigation/EvidencePanel";
import { OrchestrationCanvas } from "@/features/investigation/OrchestrationCanvas";
import * as Tabs from "@radix-ui/react-tabs";

export function InvestigationPage() {
  const navigate = useNavigate();
  const { selectedFixture } = useUiStore();
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const pipeline = useMutation({
    mutationFn: (id: string) => postAnalyzePipeline(id, "analyze_risk", true),
    onSuccess: () => {
      setCursor(0);
      setPlaying(true);
    },
  });

  useEffect(() => {
    pipeline.mutate(selectedFixture);
  }, [selectedFixture, pipeline]);

  const trace = pipeline.data?.trace;
  const events = trace?.events ?? [];
  const agents = trace?.agents ?? [];
  const toolCalls = trace?.tool_calls ?? [];
  const evidence = trace?.evidence ?? [];
  const summary = trace?.summary;

  useEffect(() => {
    if (playing && events.length) {
      timer.current = setInterval(() => {
        setCursor((c) => {
          if (c >= events.length - 1) {
            setPlaying(false);
            return c;
          }
          return c + 1;
        });
      }, 650);
    }
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, events.length]);

  function startReplay() {
    if (cursor >= events.length - 1) setCursor(0);
    setPlaying(true);
  }

  const filteredTools = useMemo(
    () =>
      selectedAgent ? toolCalls.filter((t) => t.agent === selectedAgent) : toolCalls,
    [toolCalls, selectedAgent],
  );

  const companyName =
    (trace?.company?.name as string | undefined) || selectedFixture || "目标企业";
  const completeness = summary?.completeness;

  return (
    <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-5 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate("/workbench")}>
            <ArrowLeft />
            返回工作台
          </Button>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              {companyName}
            </h1>
            <p className="text-xs text-muted-foreground">
              多 Agent 调查工作台 · 展示分类 / 规划 / 研究 / 写作 的真实协作过程
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {summary?.grade ? <GradeBadge grade={summary.grade} /> : null}
          {summary?.score != null ? (
            <StatusChip tone="neutral">危险度 {summary.score}</StatusChip>
          ) : null}
          {completeness != null ? (
            <StatusChip tone="neutral">
              完整度 {Math.round(completeness * 100)}%
            </StatusChip>
          ) : null}
          {summary?.data_gaps ? (
            <StatusChip tone="bad">{summary.data_gaps} 项数据缺口</StatusChip>
          ) : null}
          <StatusChip tone={summary?.llm_used ? "ok" : "neutral"}>
            {summary?.pipeline_mode === "llm"
              ? "LLM 增强"
              : summary?.pipeline_mode === "fallback"
                ? "降级"
                : "确定性"}
          </StatusChip>
        </div>
      </div>

      {pipeline.isPending ? (
        <section className="grid place-items-center rounded-2xl border border-dashed border-border bg-card/50 py-24 text-center">
          <Network size={28} className="mb-3 animate-pulse text-primary" strokeWidth={1.75} />
          <p className="text-base font-semibold">多 Agent 研判中…</p>
          <p className="mt-1 text-sm text-muted-foreground">加载执行迹</p>
        </section>
      ) : pipeline.isError ? (
        <section className="rounded-2xl border border-destructive/30 bg-destructive/5 px-6 py-10 text-center">
          <p className="text-sm text-destructive">
            {pipeline.error instanceof Error ? pipeline.error.message : "研判失败"}
          </p>
        </section>
      ) : (
        <PanelGroup
          direction="horizontal"
          className="h-[calc(100vh-14rem)] rounded-2xl border border-border bg-card/30 p-2"
        >
          {/* 左：Agent 队列 / 编排画布 */}
          <Panel defaultSize={24} minSize={18} className="pr-2">
            <Card className="h-full">
              <Tabs.Root defaultValue="queue" className="flex h-full flex-col">
                <CardHeader className="pb-2">
                  <Tabs.List className="flex gap-1 rounded-lg bg-muted p-1">
                    <Tabs.Trigger
                      value="queue"
                      className="flex-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                    >
                      队列
                    </Tabs.Trigger>
                    <Tabs.Trigger
                      value="canvas"
                      className="flex-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                    >
                      编排画布
                    </Tabs.Trigger>
                  </Tabs.List>
                </CardHeader>
                <CardContent className="h-[calc(100%-3rem)] min-h-0 overflow-hidden pr-1">
                  <Tabs.Content
                    value="queue"
                    className="h-full space-y-2 overflow-y-auto pr-1"
                  >
                    {agents.map((a) => (
                      <AgentCard
                        key={a.role_key}
                        agent={a}
                        active={selectedAgent === a.role_key}
                        onClick={() =>
                          setSelectedAgent((s) => (s === a.role_key ? null : a.role_key))
                        }
                      />
                    ))}
                  </Tabs.Content>
                  <Tabs.Content value="canvas" className="h-full">
                    <OrchestrationCanvas
                      agents={agents}
                      selectedAgent={selectedAgent}
                      onSelect={(k) => setSelectedAgent((s) => (s === k ? null : k))}
                    />
                  </Tabs.Content>
                </CardContent>
              </Tabs.Root>
            </Card>
          </Panel>

          <PanelResizeHandle className="w-1.5 rounded bg-border/60 data-[resize-handle-state=drag]:bg-primary/50" />

          {/* 中：事件流 + 工具调用 */}
          <Panel defaultSize={46} minSize={30}>
            <div className="flex h-full flex-col gap-2 pl-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Network size={15} className="text-primary" />
                  <span className="text-sm font-semibold text-foreground">
                    Agent 事件流
                  </span>
                  <StatusChip tone="neutral">
                    {Math.min(cursor + 1, events.length)}/{events.length}
                  </StatusChip>
                </div>
                <div className="flex items-center gap-1.5">
                  {playing ? (
                    <Button variant="outline" size="sm" onClick={() => setPlaying(false)}>
                      <Pause />
                      暂停
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" onClick={startReplay}>
                      <Play />
                      回放
                    </Button>
                  )}
                  <Button variant="outline" size="sm" onClick={() => { setPlaying(false); setCursor(0); }}>
                    <RotateCcw />
                    重置
                  </Button>
                </div>
              </div>
              <Card className="shrink-0">
                <CardContent className="max-h-[46%] overflow-y-auto pt-4">
                  <EventTimeline
                    events={events}
                    cursor={cursor}
                    onJump={(seq) => {
                      setPlaying(false);
                      setCursor(seq);
                    }}
                  />
                </CardContent>
              </Card>
              <Card className="min-h-0 flex-1">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">
                    工具调用
                    {selectedAgent ? (
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        （筛选：{agents.find((a) => a.role_key === selectedAgent)?.label}）
                      </span>
                    ) : null}
                  </CardTitle>
                </CardHeader>
                <CardContent className="h-[calc(100%-3rem)] space-y-2 overflow-y-auto pr-1">
                  {filteredTools.map((t, i) => (
                    <ToolCallCard key={`${t.agent}-${t.name}-${i}`} call={t} />
                  ))}
                </CardContent>
              </Card>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1.5 rounded bg-border/60 data-[resize-handle-state=drag]:bg-primary/50" />

          {/* 右：证据面板 */}
          <Panel defaultSize={30} minSize={22} className="pl-2">
            <Card className="h-full">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-sm">
                  <span>证据面板</span>
                  <StatusChip tone="neutral">{evidence.length} 条</StatusChip>
                </CardTitle>
              </CardHeader>
              <CardContent className="h-[calc(100%-3rem)] space-y-2 overflow-y-auto pr-1">
                <EvidencePanel evidence={evidence} />
              </CardContent>
            </Card>
          </Panel>
        </PanelGroup>
      )}
    </main>
  );
}
