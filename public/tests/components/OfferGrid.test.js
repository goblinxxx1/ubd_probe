import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferGrid from "@/components/OfferGrid.vue";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: "/offers/:id", name: "offer", component: { template: "<div/>" } }],
});

function mountGrid(props) {
  return mount(OfferGrid, { props, global: { plugins: [router] } });
}

describe("OfferGrid", () => {
  it("shows loading state", () => {
    const w = mountGrid({ offers: [], loading: true, error: null });
    expect(w.text()).toContain("Завантаження");
  });
  it("shows error state", () => {
    const w = mountGrid({ offers: [], loading: false, error: "Ой" });
    expect(w.text()).toContain("Ой");
  });
  it("shows empty state", () => {
    const w = mountGrid({ offers: [], loading: false, error: null });
    expect(w.text()).toContain("Нічого не знайдено");
  });
  it("renders one card per offer", () => {
    const offers = [
      { id: 1, type: "discount", discount_type: "free", title: "A", provider: "P", target_categories: [] },
      { id: 2, type: "event", title: "B", provider: "Q", target_categories: [] },
    ];
    const w = mountGrid({ offers, loading: false, error: null });
    expect(w.findAllComponents({ name: "OfferCard" }).length).toBe(2);
  });
});
