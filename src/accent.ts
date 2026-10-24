/**
 * Accent color theme: blue / green / purple / orange. Persists in
 * localStorage and overrides the --accent / --accent-dim CSS variables on
 * <html>. Category colors (text/link/code) stay fixed so classification
 * remains visually distinct from the brand accent.
 */

export type Accent = "blue" | "green" | "purple" | "orange";

const LS_KEY = "tietie-accent";

const COLORS: Record<Accent, { main: string; dim: string }> = {
  blue: { main: "#007aff", dim: "rgba(0, 122, 255, 0.18)" },
  green: { main: "#34c759", dim: "rgba(52, 199, 89, 0.18)" },
  purple: { main: "#af52de", dim: "rgba(175, 82, 222, 0.18)" },
  orange: { main: "#ff9500", dim: "rgba(255, 149, 0, 0.18)" },
};

const subs = new Set<() => void>();
let current: Accent = read();

function read(): Accent {
  const v = localStorage.getItem(LS_KEY);
  return v === "green" || v === "purple" || v === "orange" ? v : "blue";
}

function apply() {
  const c = COLORS[current];
  document.documentElement.style.setProperty("--accent", c.main);
  document.documentElement.style.setProperty("--accent-dim", c.dim);
}

export function getAccent(): Accent {
  return current;
}

export function setAccent(a: Accent) {
  current = a;
  localStorage.setItem(LS_KEY, a);
  apply();
  subs.forEach((f) => f());
}

/** Subscribe (returns unsubscribe). */
export function onAccentChange(fn: () => void): () => void {
  subs.add(fn);
  return () => subs.delete(fn);
}

apply();
