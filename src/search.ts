import { PINYIN_FIRST, PINYIN_FULL } from "./pinyinTable";

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

/** Concatenated full pinyin of the hanzi in s ("内存"→"neicun"). */
function pinyinFull(s: string): string {
  let out = "";
  for (const ch of s) {
    out += PINYIN_FULL[ch] ?? ch.toLowerCase();
  }
  return out;
}

/** True when every char of `q` appears in `target` in order ("ncr" ⊂ "npm create react"). */
function isSubsequence(q: string, target: string): boolean {
  let i = 0;
  for (const ch of target) {
    if (i < q.length && ch === q[i]) i++;
  }
  return i === q.length;
}

function matchOne(content: string, preview: string, q: string): boolean {
  const c = content.toLowerCase();
  const p = preview.toLowerCase();
  if (c.includes(q) || p.includes(q)) return true;
  if (/^[a-z]+$/.test(q)) {
    // pinyin: first letters ("nz"→内存) and full syllables ("neicun"→内存)
    if (pinyinInitials(content).includes(q) || pinyinFull(content).includes(q)) return true;
    if (preview && (pinyinInitials(preview).includes(q) || pinyinFull(preview).includes(q))) {
      return true;
    }
    // letter subsequence over the raw content ("ncr" ⊂ "npm create react")
    if (q.length >= 2 && (isSubsequence(q, c) || (preview && isSubsequence(q, p)))) {
      return true;
    }
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
