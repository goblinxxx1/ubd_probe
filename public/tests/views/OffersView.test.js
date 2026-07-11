import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OffersView from "@/views/OffersView.vue";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1, type: "event", title: "T", provider: "P", target_categories: [] }], total: 1, page: 1, size: 12 })),
}));
vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([])),
  listOffer: vi.fn(() => Promise.resolve([])),
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
});
