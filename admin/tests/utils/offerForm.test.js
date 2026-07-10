import { describe, it, expect } from "vitest";
import { validateOffer, buildOfferPayload } from "@/utils/offerForm";

const base = { type: "discount", title: "T", provider: "P", discount_type: "percent", discount_value: 50 };

describe("validateOffer", () => {
  it("passes a valid percent discount", () => {
    expect(validateOffer({ ...base })).toEqual([]);
  });
  it("requires title and provider", () => {
    const errors = validateOffer({ ...base, title: "", provider: "" });
    expect(errors.length).toBe(2);
  });
  it("requires discount_value for percent", () => {
    expect(validateOffer({ ...base, discount_value: null })).toContain("Вкажіть величину знижки");
  });
  it("forbids discount_value for events", () => {
    const errors = validateOffer({ type: "event", title: "T", provider: "P", discount_type: null, discount_value: 5 });
    expect(errors.some((e) => e.includes("лише для"))).toBe(true);
  });
  it("checks date order", () => {
    const errors = validateOffer({ ...base, valid_from: "2026-08-01", valid_until: "2026-07-01" });
    expect(errors.some((e) => e.includes("раніше"))).toBe(true);
  });
});

describe("buildOfferPayload", () => {
  it("nulls discount fields for events and maps category ids", () => {
    const payload = buildOfferPayload({
      type: "event", title: "T", provider: "P", description: "", location: "",
      valid_from: null, valid_until: null, discount_type: "percent", discount_value: 10,
      contacts: "", image_url: "", target_category_ids: [1], offer_category_ids: [2],
    });
    expect(payload.discount_type).toBe(null);
    expect(payload.discount_value).toBe(null);
    expect(payload.location).toBe(null);
    expect(payload.target_category_ids).toEqual([1]);
    expect(payload.offer_category_ids).toEqual([2]);
  });
});
