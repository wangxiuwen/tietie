import { PINYIN_FIRST } from "./pinyinTable";

/**
 * First pinyin letters of a string's hanzi (GB2312 coverage); non-hanzi
 * chars contribute their lowercased ASCII form so mixed text still matches.
 */
export function pinyinInitials(s: string): string {
  let out = "";
  for (const ch of s) {
    const py = PINYIN_FIRST[ch];
    out += py ?? (ch >= "a" && ch <= "z" ? ch : ch >= "A" && ch <= "Z" ? ch.toLowerCase() : "");
  }
  return out;
}

function matchOne(content: string, preview: string, q: string): boolean {
  if (content.toLowerCase().includes(q) || preview.toLowerCase().includes(q)) return true;
  if (/^[a-z]+$/.test(q)) {
    return (
      pinyinInitials(content).includes(q) ||
      (preview ? pinyinInitials(preview).includes(q) : false)
    );
  }
  return false;
}

/**
 * Unified search predicate. The query splits on whitespace and EVERY token
 * must hit (substring or pinyin initials) — "turing glass" only matches
 * entries containing both words, like Everything-style AND search.
 */
export function matchQuery(content: string, preview: string, query: string): boolean {
  const qs = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (qs.length === 0) return true;
  return qs.every((q) => matchOne(content, preview, q));
}
