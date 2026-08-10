import { describe, it, expect } from "vitest";
import { enumLabel, formatDate, offerBadge, discountText } from "@/utils/format";
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
  it("special_price → Спеціальна ціна label", () => {
    expect(offerBadge({ type: "discount", discount_type: "special_price", discount_value: 499 })).toEqual({ text: "Спеціальна ціна", kind: "discount" });
  });
});

describe("discountText", () => {
  it("free → Безкоштовно", () => {
    expect(discountText({ discount_type: "free" })).toBe("Безкоштовно");
  });
  it("percent → −N%", () => {
    expect(discountText({ discount_type: "percent", discount_value: "10.00" })).toBe("−10%");
  });
  it("fixed → −N ₴", () => {
    expect(discountText({ discount_type: "fixed", discount_value: 200 })).toBe("−200 ₴");
  });
  it("special_price → Ціна N ₴", () => {
    expect(discountText({ discount_type: "special_price", discount_value: 499 })).toBe("Ціна 499 ₴");
  });
  it("no type → Знижка", () => {
    expect(discountText({ discount_type: null })).toBe("Знижка");
  });
});
