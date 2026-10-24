import React from "react";

/**
 * Render `text` with every whitespace-separated query token highlighted
 * (case-insensitive substring, matching the search predicate semantics).
 * Tokens are regex-escaped; empty text renders nothing.
 */
export function HighlightText({ text, query }: { text: string; query: string }) {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!text) return null;
  if (tokens.length === 0) return <>{text}</>;

  const escaped = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(re);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark className="hl" key={i}>
            {p}
          </mark>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </>
  );
}
