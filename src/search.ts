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

/**
 * Unified search predicate: plain substring on content/preview (original
 * behavior), plus pinyin-initials substring when the query is pure ASCII
 * letters — "nz" finds 「内存」.
 */
export function matchQuery(content: string, preview: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (content.toLowerCase().includes(q) || preview.toLowerCase().includes(q)) return true;
  if (/^[a-z]+$/.test(q)) {
    return (
      pinyinInitials(content).includes(q) ||
      (preview ? pinyinInitials(preview).includes(q) : false)
    );
  }
  return false;
}
