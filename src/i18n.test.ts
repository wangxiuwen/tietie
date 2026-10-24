import { describe, expect, it } from "vitest";
import { en, zh } from "./i18n";

describe("i18n dictionaries", () => {
  it("zh and en expose exactly the same key set (no missing translations)", () => {
    const zk = Object.keys(zh).sort();
    const ek = Object.keys(en).sort();
    const onlyZh = zk.filter((k) => !(k in en));
    const onlyEn = ek.filter((k) => !(k in zh));
    expect(
      { onlyZh, onlyEn, zhCount: zk.length, enCount: ek.length },
      `key drift: onlyZh=${JSON.stringify(onlyZh)} onlyEn=${JSON.stringify(onlyEn)}`,
    ).toEqual({ onlyZh: [], onlyEn: [], zhCount: zk.length, enCount: ek.length });
  });
  it("no empty values in either language", () => {
    for (const [k, v] of Object.entries(zh)) expect(v.length, `zh[${k}] empty`).toBeGreaterThan(0);
    for (const [k, v] of Object.entries(en)) expect(v.length, `en[${k}] empty`).toBeGreaterThan(0);
  });
});
