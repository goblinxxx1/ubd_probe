import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OffersView from "@/views/OffersView.vue";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1, type: "event", title: "T", provider: "P", target_categories: [] }], total: 1, page: 1, size: 12 })),
  facets: vi.fn(() => Promise.resolve({ target_categories: [], offer_categories: [], types: [], locations: [] })),
}));
import * as offers from "@/api/offers";

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: OffersView },
      { path: "/offers/:id", name: "offer", component: { template: "<div/>" } },
    ],
  });
  return router;
}

describe("OffersView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads offers on mount", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 12 });
  });

  it("applying filters updates the query and refetches", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    wrapper.getComponent({ name: "OfferFilters" }).vm.$emit("apply", { type: "discount", q: "кава" });
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({ type: "discount", q: "кава" });
    expect(offers.list).toHaveBeenLastCalledWith({ page: 1, size: 12, type: "discount", q: "кава" });
  });

  it("renders a persistent filter sidebar next to the content", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const w = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.get(".offers__rail").exists()).toBe(true);
    expect(w.get(".offers__main").exists()).toBe(true);
    expect(w.getComponent({ name: "OfferFilters" }).exists()).toBe(true);
  });

  it("toggles the mobile filter drawer open and closed", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const w = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.vm.filtersOpen).toBe(false);
    expect(w.get(".offers__rail").classes()).not.toContain("is-open");
    await w.get(".offers__toggle").trigger("click");
    expect(w.vm.filtersOpen).toBe(true);
    expect(w.get(".offers__rail").classes()).toContain("is-open");
    await w.get(".offers__rail-close").trigger("click");
    expect(w.vm.filtersOpen).toBe(false);
  });

  it("changing page updates the query", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    wrapper.vm.onPage(2);
    await flushPromises();
    expect(router.currentRoute.value.query.page).toBe("2");
  });

  it("renders the load-more control in the main column", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const w = mount(OffersView, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.getComponent({ name: "LoadMore" }).exists()).toBe(true);
  });
});
