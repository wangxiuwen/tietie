import { describe, expect, it } from "vitest";
import { hexToRgb } from "./color";

describe("hexToRgb", () => {
  it("converts 6-digit hex", () => {
    expect(hexToRgb("#3b82f6")).toBe("rgb(59, 130, 246)");
    expect(hexToRgb("#34c759")).toBe("rgb(52, 199, 89)");
  });
  it("accepts missing # and surrounding spaces", () => {
    expect(hexToRgb(" 3B82F6 ")).toBe("rgb(59, 130, 246)");
  });
  it("passes non-colors through untouched", () => {
    expect(hexToRgb("#abc")).toBe("#abc"); // 3-digit not supported
    expect(hexToRgb("not a color")).toBe("not a color");
    expect(hexToRgb("#12345g")).toBe("#12345g");
  });
});
