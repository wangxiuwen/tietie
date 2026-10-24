/**
 * Global font scale: compact (0.9) / standard (1) / large (1.15).
 * Persists in localStorage and sets --fs on <html> so every rem-free
 * font-size (calc(px * var(--fs))) scales together.
 */

export type FontScale = "compact" | "standard" | "large";

const LS_KEY = "tietie-font-scale";
const VALUES: Record<FontScale, string> = { compact: "0.9", standard: "1", large: "1.15" };

const subs = new Set<() => void>();
let current: FontScale = read();

function read(): FontScale {
  const v = localStorage.getItem(LS_KEY);
  return v === "compact" || v === "large" ? v : "standard";
}

function apply() {
  document.documentElement.style.setProperty("--fs", VALUES[current]);
}

export function getFontScale(): FontScale {
  return current;
}

export function setFontScale(s: FontScale) {
  current = s;
  localStorage.setItem(LS_KEY, s);
  apply();
  subs.forEach((f) => f());
}

/** Subscribe (returns unsubscribe) so views can re-render on change. */
export function onFontScaleChange(fn: () => void): () => void {
  subs.add(fn);
  return () => subs.delete(fn);
}

apply();
