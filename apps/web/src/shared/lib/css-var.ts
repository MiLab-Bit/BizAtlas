/** Read a CSS custom property from :root (supports `H S% L%` or full color). */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") {
    return fallback.includes("%") || /^\d/.test(fallback) ? `hsl(${fallback})` : fallback;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  if (raw.startsWith("#") || raw.startsWith("rgb") || raw.startsWith("hsl")) return raw;
  return `hsl(${raw})`;
}

/** Apply alpha to an `hsl(...)` / `#hex` color string for canvas libraries. */
export function withAlpha(color: string, alpha: number): string {
  const m = color.match(/^hsl\((.+)\)$/);
  if (m) return `hsl(${m[1]} / ${alpha})`;
  return color;
}
