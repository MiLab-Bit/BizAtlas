import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { cssVar, withAlpha } from "@/shared/lib/css-var";

type Dim = { id: string; score: number; weight: number };

export function RiskRadar({
  dimensions,
  onDimensionClick,
}: {
  dimensions: Dim[];
  onDimensionClick?: (id: string) => void;
}) {
  const option = useMemo(() => {
    const labels = dimensions.map((d) => d.id);
    const values = dimensions.map((d) => Math.min(100, Number(d.score) || 0));
    const primary = cssVar("--primary", "221 83% 53%");
    const destructive = cssVar("--destructive", "347 77% 50%");
    const foreground = cssVar("--foreground", "222 47% 11%");
    const muted = cssVar("--muted-foreground", "215 16% 47%");
    const border = cssVar("--border", "214 20% 90%");

    return {
      color: [primary],
      backgroundColor: "transparent",
      tooltip: { trigger: "item" },
      radar: {
        indicator: labels.map((name) => ({ name, max: 100 })),
        splitNumber: 4,
        axisName: {
          color: muted,
          fontSize: 12,
          formatter: (name: string) => `{a|${name}}`,
          rich: { a: { color: foreground, fontWeight: 600 } },
        },
        splitLine: { lineStyle: { color: border } },
        splitArea: {
          areaStyle: {
            color: ["hsla(210,20%,98%,0.9)", "hsla(210,20%,96%,0.95)"],
          },
        },
        axisLine: { lineStyle: { color: border } },
        triggerEvent: true,
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: values,
              name: "危险度",
              areaStyle: { color: withAlpha(primary, 0.16) },
              lineStyle: { width: 2, color: primary },
              itemStyle: { color: destructive },
              symbol: "circle",
              symbolSize: 5,
            },
          ],
        },
      ],
    };
  }, [dimensions]);

  return (
    <div>
      <ReactECharts
        option={option}
        style={{ height: 280, width: "100%" }}
        opts={{ renderer: "svg" }}
        onEvents={{
          click: (params: { name?: string }) => {
            if (params?.name && onDimensionClick) onDimensionClick(String(params.name));
          },
        }}
      />
      <p className="mt-1 text-xs text-muted-foreground">点击维度名可下钻归因</p>
    </div>
  );
}
