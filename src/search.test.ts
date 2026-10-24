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
});
