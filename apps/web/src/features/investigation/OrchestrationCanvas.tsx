import { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

/** 与 trace.agents 元素同构（investigation 工作台已用），仅取画布所需字段。 */
export interface CanvasAgent {
  role_key: string;
  label: string;
  status: string; // queued|running|completed|failed|blocked|waiting_review
  mode: string; // deterministic|llm|fallback
  ok: boolean;
  task: string;
  inputs: number;
  outputs: number;
  evidence: number;
  summary: string;
}

type AgentNodeData = {
  label: string;
  status: string;
  mode: string;
  ok: boolean;
  task: string;
  inputs: number;
  outputs: number;
  evidence: number;
  summary: string;
};

type AgentFlowNode = Node<AgentNodeData, "agent">;

// 真实管线拓扑：评分内核 → 分类 → 规划 → 研究 → 写作（线性依赖）。
const ORDER = ["scoring", "classifier", "planner", "researcher", "writer"];

function modeTone(mode: string): string {
  if (mode === "llm") return "bg-emerald-500/15 text-emerald-600";
  if (mode === "fallback") return "bg-amber-500/15 text-amber-600";
  return "bg-slate-500/15 text-slate-600";
}

function statusRing(status: string, selected: boolean): string {
  if (selected) return "ring-2 ring-primary";
  if (status === "failed") return "ring-1 ring-red-400";
  if (status === "completed") return "ring-1 ring-emerald-400/70";
  if (status === "running") return "ring-1 ring-blue-400";
  return "ring-1 ring-border";
}

function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  return (
    <div
      className={`w-[210px] rounded-xl border border-border bg-card px-3 py-2.5 shadow-sm transition ${statusRing(
        data.status,
        !!selected,
      )}`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !bg-slate-400" />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-semibold leading-tight text-foreground">
          {data.label}
        </span>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${modeTone(data.mode)}`}
        >
          {data.mode === "llm" ? "LLM" : data.mode === "fallback" ? "降级" : "确定性"}
        </span>
      </div>
      <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
        {data.task}
      </p>
      <p className="mt-1.5 truncate text-[11px] font-medium text-foreground/80">
        {data.summary}
      </p>
      <div className="mt-2 flex gap-3 text-[10px] text-muted-foreground">
        <span>入 {data.inputs}</span>
        <span>出 {data.outputs}</span>
        <span>证 {data.evidence}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !bg-slate-400" />
    </div>
  );
}

const nodeTypes: NodeTypes = { agent: AgentNode };

function buildNodes(agents: CanvasAgent[], selectedAgent: string | null): AgentFlowNode[] {
  const byKey = Object.fromEntries(agents.map((a) => [a.role_key, a]));
  return ORDER.filter((k) => byKey[k]).map((k, i) => {
    const a = byKey[k];
    return {
      id: k,
      type: "agent",
      position: { x: 0, y: i * 150 },
      selected: selectedAgent === k,
      data: {
        label: a.label,
        status: a.status,
        mode: a.mode,
        ok: a.ok,
        task: a.task,
        inputs: a.inputs,
        outputs: a.outputs,
        evidence: a.evidence,
        summary: a.summary,
      },
    };
  });
}

function buildEdges(agents: CanvasAgent[]): Edge[] {
  const byKey = Object.fromEntries(agents.map((a) => [a.role_key, a]));
  const order = ORDER.filter((k) => byKey[k]);
  return order.slice(0, -1).map((k, i) => ({
    id: `e-${k}-${order[i + 1]}`,
    source: k,
    target: order[i + 1],
    animated: true,
    style: { stroke: "#94a3b8", strokeWidth: 1.5 },
  }));
}

export function OrchestrationCanvas({
  agents,
  selectedAgent,
  onSelect,
}: {
  agents: CanvasAgent[];
  selectedAgent: string | null;
  onSelect: (roleKey: string) => void;
}) {
  const initialNodes = useMemo(() => buildNodes(agents, selectedAgent), [agents, selectedAgent]);
  const initialEdges = useMemo(() => buildEdges(agents), [agents]);
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentFlowNode>(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState<Edge>(initialEdges);

  // agents / 选中态变化 → 同步节点（保留位置，仅更新 data/selected）
  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const src = agents.find((a) => a.role_key === n.id);
        if (!src) return n;
        return {
          ...n,
          selected: selectedAgent === n.id,
          data: {
            label: src.label,
            status: src.status,
            mode: src.mode,
            ok: src.ok,
            task: src.task,
            inputs: src.inputs,
            outputs: src.outputs,
            evidence: src.evidence,
            summary: src.summary,
          },
        };
      }),
    );
  }, [agents, selectedAgent, setNodes]);

  return (
    <div className="h-full w-full overflow-hidden rounded-lg">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background gap={16} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable className="!bg-card" />
      </ReactFlow>
    </div>
  );
}
