import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import OfferBadge from "@/components/OfferBadge.vue";

describe("OfferBadge", () => {
  it("renders event badge", () => {
    const w = mount(OfferBadge, { props: { offer: { type: "event" } } });
    expect(w.text()).toBe("Подія");
    expect(w.get("span").classes()).toContain("badge--event");
  });
  it("renders percent discount", () => {
    const w = mount(OfferBadge, { props: { offer: { type: "discount", discount_type: "percent", discount_value: 50 } } });
    expect(w.text()).toBe("−50%");
    expect(w.get("span").classes()).toContain("badge--discount");
  });
});
