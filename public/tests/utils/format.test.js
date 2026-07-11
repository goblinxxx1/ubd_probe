import { describe, it, expect } from "vitest";
import { enumLabel, formatDate, offerBadge } from "@/utils/format";
import { OFFER_TYPES } from "@/constants/enums";

describe("enumLabel", () => {
  it("maps value to label, falls back to raw", () => {
    expect(enumLabel(OFFER_TYPES, "event")).toBe("Подія");
    expect(enumLabel(OFFER_TYPES, "???")).toBe("???");
  });
});

describe("formatDate", () => {
  it("formats ISO date as dd.mm.yyyy, empty for null", () => {
    expect(formatDate("2026-07-01")).toBe("01.07.2026");
    expect(formatDate(null)).toBe("");
  });
});

describe("offerBadge", () => {
  it("event → Подія", () => {
    expect(offerBadge({ type: "event" })).toEqual({ text: "Подія", kind: "event" });
  });
  it("free → Безкоштовно", () => {
    expect(offerBadge({ type: "discount", discount_type: "free" })).toEqual({ text: "Безкоштовно", kind: "free" });
  });
  it("percent → −N%", () => {
    expect(offerBadge({ type: "discount", discount_type: "percent", discount_value: "50.00" })).toEqual({ text: "−50%", kind: "discount" });
  });
  it("fixed → −N ₴", () => {
    expect(offerBadge({ type: "discount", discount_type: "fixed", discount_value: 200 })).toEqual({ text: "−200 ₴", kind: "discount" });
  });
  it("discount with no type → Знижка", () => {
    expect(offerBadge({ type: "discount", discount_type: null })).toEqual({ text: "Знижка", kind: "discount" });
  });
});
