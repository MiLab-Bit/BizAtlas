import { Graph } from "@antv/g6";
import { useEffect, useRef } from "react";
import { cssVar } from "@/shared/lib/css-var";

type Node = { id: string; name: string; category?: string; risk?: string };
type Edge = { source: string; target: string; rel?: string };

function riskColors() {
  return {
    self: cssVar("--primary", "221 83% 53%"),
    normal: cssVar("--muted-foreground", "215 16% 47%"),
    warn: cssVar("--grade-orange", "21 90% 48%"),
    high: cssVar("--destructive", "347 77% 50%"),
  };
}

export function GuaranteeGraph({
  nodes,
  edges,
  note,
}: {
  nodes: Node[];
  edges: Edge[];
  note?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const colors = riskColors();
    const foreground = cssVar("--foreground", "222 47% 11%");
    const muted = cssVar("--muted-foreground", "215 16% 47%");
    const border = cssVar("--border", "214 20% 90%");

    const graph = new Graph({
      container: el,
      width: el.clientWidth || 640,
      height: 300,
      data: {
        nodes: nodes.map((n) => ({
          id: n.id,
          data: { label: n.name, risk: n.risk || "normal" },
        })),
        edges: edges.map((e, i) => ({
          id: `e-${i}`,
          source: e.source,
          target: e.target,
          data: { rel: e.rel || "担保" },
        })),
      },
      layout: {
        type: "force",
        preventOverlap: true,
        linkDistance: 100,
      },
      node: {
        style: {
          size: (d: { data?: { risk?: string } }) => (d.data?.risk === "self" ? 42 : 32),
          fill: (d: { data?: { risk?: string } }) =>
            colors[d.data?.risk as keyof typeof colors] || colors.normal,
          labelText: (d: { data?: { label?: string } }) => d.data?.label || "",
          labelPlacement: "bottom",
          labelFill: foreground,
          labelFontSize: 11,
          stroke: "#fff",
          lineWidth: 1.5,
        },
      },
      edge: {
        style: {
          stroke: border,
          endArrow: true,
          labelText: (d: { data?: { rel?: string } }) => d.data?.rel || "",
          labelFill: muted,
          labelFontSize: 10,
        },
      },
      behaviors: ["drag-element", "zoom-canvas", "drag-canvas"],
    });

    void graph.render();
    return () => {
      graph.destroy();
    };
  }, [nodes, edges]);

  return (
    <div>
      <div ref={ref} className="h-[300px] w-full overflow-hidden rounded-lg border border-border" />
      {note ? <p className="mt-2 text-sm text-muted-foreground">{note}</p> : null}
      <p className="mt-1 text-xs text-muted-foreground">AntV G6 · 可拖拽 / 缩放</p>
    </div>
  );
}
