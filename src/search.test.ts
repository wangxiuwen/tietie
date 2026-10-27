import { describe, expect, it } from "vitest";
import { matchQuery, pinyinInitials } from "./search";

describe("pinyinInitials", () => {
  it("takes first letters of hanzi", () => {
    expect(pinyinInitials("内存")).toBe("nc");
  });
  it("keeps ascii letters lowercased in mixed text", () => {
    expect(pinyinInitials("Win 内存")).toBe("winnc");
  });
  it("drops digits and punctuation", () => {
    expect(pinyinInitials("v2.0 上线")).toBe("vsx");
  });
});

describe("matchQuery", () => {
  it("matches plain substring", () => {
    expect(matchQuery("hello world", "", "hello")).toBe(true);
    expect(matchQuery("hello world", "", "goodbye")).toBe(false);
  });
  it("matches pinyin initials (sx → 上线单)", () => {
    expect(matchQuery("上线单", "", "sx")).toBe(true);
  });
  it("matches full pinyin (neicun → 内存)", () => {
    expect(matchQuery("内存不足", "", "neicun")).toBe(true);
  });
  it("matches letter subsequence (tln ⊂ turing-llm-next)", () => {
    expect(matchQuery("turing-llm-next", "", "tln")).toBe(true);
  });
  it("falls back to the preview when content misses", () => {
    expect(matchQuery("", "预览：内存条", "nc")).toBe(true);
  });
  it("space-split AND: every token must hit", () => {
    expect(matchQuery("turing llm next", "", "turing llm")).toBe(true);
    expect(matchQuery("turing llm next", "", "turing zzzz")).toBe(false);
  });
  it("empty query matches everything", () => {
    expect(matchQuery("anything", "", "   ")).toBe(true);
  });
  it("-token excludes entries matching the term (direction 97)", () => {
    expect(matchQuery("turing llm next", "", "llm -next")).toBe(false);
    expect(matchQuery("turing llm glass", "", "llm -next")).toBe(true);
  });
  it("exclusion-only query keeps everything else", () => {
    expect(matchQuery("hello", "", "-zzzz")).toBe(true);
    expect(matchQuery("hello", "", "-hello")).toBe(false);
  });
  it("bare minus is ignored", () => {
    expect(matchQuery("hello world", "", "- hello")).toBe(true);
  });
  it("kind prefix filters by type (direction 157)", () => {
    expect(matchQuery("hello", "", "text:", "text")).toBe(true);
    expect(matchQuery("hello", "", "text:", "link")).toBe(false);
    expect(matchQuery("1100x760", "", "img:", "image")).toBe(true);
    expect(matchQuery("1100x760", "", "img:", "text")).toBe(false);
    expect(matchQuery("https://a.com", "", "link:", "link")).toBe(true);
    expect(matchQuery("plain text", "", "link:", "text")).toBe(false);
    // prefix + term AND-combines, and kind prefix mixes with other tokens
    expect(matchQuery("api endpoint doc", "", "text:api", "text")).toBe(true);
    expect(matchQuery("api endpoint doc", "", "text:zzz", "text")).toBe(false);
    expect(matchQuery("glass spec v2", "", "text:glass v2", "text")).toBe(true);
    expect(matchQuery("glass spec v2", "", "text:glass v3", "text")).toBe(false);
    // unknown kind caller (no kind passed): prefix filters still constrain
    expect(matchQuery("hello", "", "text:")).toBe(false);
  });
});
