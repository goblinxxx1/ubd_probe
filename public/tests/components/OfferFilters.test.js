import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import OfferFilters from "@/components/OfferFilters.vue";

function mountFilters(modelValue = {}) {
  return mount(OfferFilters, {
    props: {
      modelValue,
      targetCategories: [{ id: 1, name: "УБД" }, { id: 2, name: "Ветерани" }],
      offerCategories: [{ id: 5, name: "Розваги" }],
      locations: ["Київ", "Львів", "Одеса"],
    },
  });
}

describe("OfferFilters (sidebar)", () => {
  it("renders each option with the checkbox to the LEFT of its label text", () => {
    const w = mountFilters({});
    const opt = w.get(".filters__opt");
    // first element child of the row is the checkbox, text comes after it
    expect(opt.element.firstElementChild.tagName).toBe("INPUT");
    expect(opt.get("input").attributes("type")).toBe("checkbox");
  });

  it("seeds checkbox state from modelValue (single value normalised to array)", () => {
    const w = mountFilters({ target_category: "1", type: ["discount", "event"] });
    expect(w.vm.sel.target_category).toEqual(["1"]);
    expect(w.vm.sel.type).toEqual(["discount", "event"]);
  });

  it("live-applies a multi target-category selection as an array", () => {
    const w = mountFilters({});
    w.vm.sel.target_category = ["1", "2"];
    w.vm.apply();
    expect(w.emitted().apply[0][0]).toEqual({ target_category: ["1", "2"] });
  });

  it("emits every active facet together", () => {
    const w = mountFilters({});
    Object.assign(w.vm.sel, {
      type: ["event"], target_category: ["1"], offer_category: ["5"],
      location: ["Київ", "Одеса"], q: "музей",
    });
    w.vm.apply();
    expect(w.emitted().apply[0][0]).toEqual({
      type: ["event"], target_category: ["1"], offer_category: ["5"],
      location: ["Київ", "Одеса"], q: "музей",
    });
  });

  it("toggling a checkbox in the DOM fires a live apply", async () => {
    const w = mountFilters({});
    await w.get(".filters__opt input[type=checkbox]").setValue(true);
    expect(w.emitted().apply).toBeTruthy();
    expect(w.emitted().apply[0][0].target_category).toEqual(["1"]);
  });

  it("counts active facets from modelValue (arrays and scalars)", () => {
    expect(mountFilters({ target_category: ["1", "2"], q: "кава" }).vm.activeCount).toBe(2);
    expect(mountFilters({ location: [] }).vm.activeCount).toBe(0);
    expect(mountFilters({ type: ["discount"], location: ["Київ"] }).vm.activeCount).toBe(2);
  });

  it("reset emits empty filters", () => {
    const w = mountFilters({ type: ["discount"] });
    w.vm.reset();
    expect(w.emitted().apply[0][0]).toEqual({});
  });
});
