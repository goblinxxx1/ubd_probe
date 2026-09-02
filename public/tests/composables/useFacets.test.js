import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import { useFacets } from "@/composables/useFacets";

vi.mock("@/api/offers", () => ({
  facets: vi.fn(() => Promise.resolve({
    target_categories: [{ id: 1, name: "УБД", count: 2 }],
    offer_categories: [{ id: 5, name: "Розваги", count: 1 }],
    types: [{ value: "discount", count: 3 }],
    locations: [{ name: "Київ", count: 2 }],
  })),
}));
import * as offers from "@/api/offers";

const Host = { setup: () => useFacets(), render: () => h("div") };

async function mountAt(query) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: Host }] });
  router.push({ path: "/", query });
  await router.isReady();
  const wrapper = mount(Host, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe("useFacets", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads facets on mount and exposes each group", async () => {
    const { wrapper } = await mountAt({});
    expect(offers.facets).toHaveBeenCalledWith({});
    expect(wrapper.vm.targetCategories[0].name).toBe("УБД");
    expect(wrapper.vm.types[0].value).toBe("discount");
    expect(wrapper.vm.locations[0].count).toBe(2);
  });

  it("refetches with the active filters when the query changes", async () => {
    const { router } = await mountAt({});
    await router.push({ path: "/", query: { location: "Київ" } });
    await flushPromises();
    expect(offers.facets).toHaveBeenLastCalledWith({ location: "Київ" });
  });

  it("keeps the previous snapshot when a refetch fails", async () => {
    const { wrapper, router } = await mountAt({});
    offers.facets.mockRejectedValueOnce(new Error("boom"));
    await router.push({ path: "/", query: { q: "x" } });
    await flushPromises();
    expect(wrapper.vm.targetCategories[0].name).toBe("УБД");   // unchanged, not cleared
  });

  it("discards a stale in-flight facets response when the query changes", async () => {
    const { wrapper, router } = await mountAt({});   // initial snapshot: УБД
    let resolveSlow;
    const slow = new Promise((r) => { resolveSlow = r; });
    offers.facets.mockReturnValueOnce(slow);         // this refetch hangs
    await router.push({ path: "/", query: { location: "Київ" } });
    await flushPromises();
    // a newer refetch resolves first (default mock -> УБД); then the stale one resolves
    await router.push({ path: "/", query: { location: "Львів" } });
    await flushPromises();
    resolveSlow({ target_categories: [{ id: 9, name: "СТАРЕ", count: 1 }], offer_categories: [], types: [], locations: [] });
    await flushPromises();
    expect(wrapper.vm.targetCategories[0].name).toBe("УБД");   // stale response discarded, not applied
  });
});
