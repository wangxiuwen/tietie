// Platform detection so shortcut hints show the right modifier names.
// macOS keeps the ⌘⇧ vocabulary; Windows/Linux render Ctrl/Win/Super.
export const IS_MAC =
  navigator.userAgent.includes("Macintosh") ||
  (navigator.platform || "").toLowerCase().startsWith("mac");

/** Primary modifier glyph for kbd hints: ⌘ on macOS, Ctrl elsewhere. */
export const MOD = IS_MAC ? "⌘" : "Ctrl";

/** Name of the Super/Meta key on this platform, for plain-text hints. */
export const SUPER_LABEL = IS_MAC ? "⌘" : "Win";
