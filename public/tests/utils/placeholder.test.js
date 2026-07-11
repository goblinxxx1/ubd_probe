import { describe, it, expect } from "vitest";
import { placeholderText, placeholderDataUri } from "@/utils/placeholder";

describe("placeholderText", () => {
  it("says 'безкоштовно' for events and free", () => {
    expect(placeholderText({ type: "event", discount_type: null })).toBe("безкоштовно для УБД");
    expect(placeholderText({ type: "discount", discount_type: "free" })).toBe("безкоштовно для УБД");
  });
  it("says 'знижка' otherwise", () => {
    expect(placeholderText({ type: "discount", discount_type: "percent" })).toBe("знижка для УБД");
  });
});

describe("placeholderDataUri", () => {
  it("returns an svg data uri containing the text", () => {
    const uri = placeholderDataUri({ type: "event", discount_type: null });
    expect(uri.startsWith("data:image/svg+xml,")).toBe(true);
    expect(decodeURIComponent(uri)).toContain("безкоштовно для УБД");
  });
});
