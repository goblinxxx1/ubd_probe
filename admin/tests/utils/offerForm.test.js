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
      type: "event", title: "T", provider: "P", description: "", locations: ["Київ"],
      valid_from: null, valid_until: null, discount_type: "percent", discount_value: 10,
      site_url: "", article_url: "", image_url: "", target_category_ids: [1], offer_category_ids: [2],
    });
    expect(payload.discount_type).toBe(null);
    expect(payload.discount_value).toBe(null);
    expect(payload.locations).toEqual(["Київ"]);
    expect(payload.target_category_ids).toEqual([1]);
    expect(payload.offer_category_ids).toEqual([2]);
  });

  it("defaults locations to an empty array and drops the old location key", () => {
    const p = buildOfferPayload({ type: "event", title: "T", provider: "P" });
    expect(p.locations).toEqual([]);
    expect("location" in p).toBe(false);
  });
});

describe("discounts list", () => {
  it("passes discounts through the payload", () => {
    const form = { type: "discount", title: "T", provider: "P",
      discount_type: "percent", discount_value: 15,
      discounts: [{ label: "МВС", discount_type: "percent", discount_value: 10 }],
      locations: [], target_category_ids: [], offer_category_ids: [] };
    const payload = buildOfferPayload(form);
    expect(payload.discounts).toEqual([{ label: "МВС", discount_type: "percent", discount_value: 10 }]);
  });

  it("rejects a discount row with a value but free type", () => {
    const form = { type: "discount", title: "T", provider: "P",
      discount_type: "percent", discount_value: 15,
      discounts: [{ label: "x", discount_type: "free", discount_value: 5 }],
      locations: [], target_category_ids: [], offer_category_ids: [] };
    expect(validateOffer(form).length).toBeGreaterThan(0);
  });
});

describe("offer url fields", () => {
  it("payload carries site_url/article_url, not contacts", () => {
    const p = buildOfferPayload({ ...base, site_url: "https://ex.com", article_url: "" });
    expect(p.site_url).toBe("https://ex.com");
    expect(p.article_url).toBe(null);
    expect("contacts" in p).toBe(false);
  });
  it("rejects a non-URL site", () => {
    expect(validateOffer({ ...base, site_url: "nope" })).toContain(
      "«Сайт» має починатися з http:// або https://"
    );
  });
  it("accepts empty urls", () => {
    expect(validateOffer({ ...base, site_url: "", article_url: "" })).toEqual([]);
  });
});
