import type { ReactNode } from "react";

export type Citation = {
  id?: string;
  label?: string;
  page?: number | null;
  tier?: string;
  value?: number | null;
};

function tipOf(c: Citation) {
  const parts = [
    c.value != null ? `值 ${c.value}` : null,
    c.id ? `来源 ${c.id}` : null,
    c.tier ? c.tier : null,
    c.page != null ? `页 ${c.page}` : null,
  ].filter(Boolean);
  return parts.join(" · ") || "无溯源";
}

/** 指标名超链接：悬停看一行溯源，不另开抽屉 */
export function SourceLink({
  citation,
  children,
}: {
  citation: Citation;
  children?: ReactNode;
}) {
  return (
    <a
      className="font-medium text-primary underline decoration-primary/30 underline-offset-2 hover:decoration-primary"
      href={`#src-${encodeURIComponent(citation.label || citation.id || "m")}`}
      title={tipOf(citation)}
      onClick={(e) => e.preventDefault()}
    >
      {children ?? citation.label}
    </a>
  );
}

/** 把正文里出现的指标名替换为溯源超链接 */
export function LinkedText({
  text,
  citations,
}: {
  text: string;
  citations: Citation[];
}) {
  if (!text) return null;
  const labels = Array.from(
    new Set(
      citations
        .map((c) => c.label)
        .filter((x): x is string => Boolean(x))
        .sort((a, b) => b.length - a.length),
    ),
  );
  if (!labels.length) return <>{text}</>;

  const byLabel = new Map<string, Citation>();
  for (const c of citations) {
    if (c.label && !byLabel.has(c.label)) byLabel.set(c.label, c);
  }

  const parts: ReactNode[] = [];
  let rest = text;
  let key = 0;
  while (rest.length) {
    let bestIdx = -1;
    let bestLabel = "";
    for (const label of labels) {
      const idx = rest.indexOf(label);
      if (idx >= 0 && (bestIdx < 0 || idx < bestIdx)) {
        bestIdx = idx;
        bestLabel = label;
      }
    }
    if (bestIdx < 0) {
      parts.push(rest);
      break;
    }
    if (bestIdx > 0) parts.push(rest.slice(0, bestIdx));
    const cite = byLabel.get(bestLabel)!;
    parts.push(
      <SourceLink key={key++} citation={cite}>
        {bestLabel}
      </SourceLink>,
    );
    rest = rest.slice(bestIdx + bestLabel.length);
  }
  return <>{parts}</>;
}
