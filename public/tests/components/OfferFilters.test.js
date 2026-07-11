import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import OfferFilters from "@/components/OfferFilters.vue";

function mountFilters(modelValue = {}) {
  return mount(OfferFilters, {
    props: {
      modelValue,
      targetCategories: [{ id: 1, name: "УБД" }],
      offerCategories: [{ id: 2, name: "Розваги" }],
    },
  });
}

describe("OfferFilters", () => {
  it("counts active filters from modelValue", () => {
    const w = mountFilters({ type: "discount", q: "кава" });
    expect(w.vm.activeCount).toBe(2);
  });

  it("apply emits cleaned filters and closes", async () => {
    const w = mountFilters({});
    w.vm.open = true;
    Object.assign(w.vm.draft, { type: "event", location: "", q: "музей" });
    w.vm.apply();
    expect(w.emitted().apply[0][0]).toEqual({ type: "event", q: "музей" });
    expect(w.vm.open).toBe(false);
  });

  it("reset emits empty filters", () => {
    const w = mountFilters({ type: "discount" });
    w.vm.reset();
    expect(w.emitted().apply[0][0]).toEqual({});
  });
});
