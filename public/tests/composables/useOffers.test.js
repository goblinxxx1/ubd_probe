import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import { useOffers } from "@/composables/useOffers";

vi.mock("@/api/offers", () => ({
  list: vi.fn((params) =>
    Promise.resolve({ items: [{ id: params.page }], total: 3, page: params.page, size: 12 })),
}));
import * as offers from "@/api/offers";

// Host component that exercises the composable and exposes its state.
const Host = {
  setup() {
    const s = useOffers();
    return s;
  },
  render() {
    return h("div");
  },
};

async function mountAt(query) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: Host }],
  });
  router.push({ path: "/", query });
  await router.isReady();
  const wrapper = mount(Host, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe("useOffers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("builds params from query, dropping empties", async () => {
    await mountAt({ type: "discount", q: "кава" });
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 12, type: "discount", q: "кава" });
  });

  it("reads page from query", async () => {
    await mountAt({ page: "3" });
    expect(offers.list).toHaveBeenCalledWith({ page: 3, size: 12 });
  });

  it("reloads when the query changes", async () => {
    const { router } = await mountAt({});
    expect(offers.list).toHaveBeenCalledTimes(1);
    await router.push({ path: "/", query: { location: "Київ" } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledTimes(2);
    expect(offers.list).toHaveBeenLastCalledWith({ page: 1, size: 12, location: "Київ" });
  });

  it("sets error on failure", async () => {
    offers.list.mockRejectedValueOnce({ message: "boom" });
    const { wrapper } = await mountAt({});
    expect(wrapper.vm.error).toBe("boom");
    expect(wrapper.vm.items).toEqual([]);
  });

  it("appends the next page on loadMore and advances hasMore", async () => {
    const { wrapper } = await mountAt({});
    expect(wrapper.vm.items).toEqual([{ id: 1 }]);
    expect(wrapper.vm.hasMore).toBe(true);
    await wrapper.vm.loadMore();
    await flushPromises();
    expect(offers.list).toHaveBeenLastCalledWith({ page: 2, size: 12 });
    expect(wrapper.vm.items).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it("stops offering more once every item is loaded", async () => {
    const { wrapper } = await mountAt({});
    await wrapper.vm.loadMore();   // page 2
    await wrapper.vm.loadMore();   // page 3 -> 3 items == total
    await flushPromises();
    expect(wrapper.vm.items.map((i) => i.id)).toEqual([1, 2, 3]);
    expect(wrapper.vm.hasMore).toBe(false);
  });

  it("resets to the base page when filters change", async () => {
    const { wrapper, router } = await mountAt({});
    await wrapper.vm.loadMore();
    await router.push({ path: "/", query: { q: "кава" } });
    await flushPromises();
    expect(wrapper.vm.items).toEqual([{ id: 1 }]);   // fresh page 1, not appended
  });

  it("discards an in-flight loadMore when filters change mid-request", async () => {
    const { wrapper, router } = await mountAt({});   // page 1 -> [{id:1}], total 3
    let resolveSlow;
    const slow = new Promise((r) => { resolveSlow = r; });
    offers.list.mockReturnValueOnce(slow);           // the loadMore fetch hangs
    const morePromise = wrapper.vm.loadMore();
    await router.push({ path: "/", query: { q: "x" } });   // load() resets the list
    await flushPromises();
    // stale loadMore now resolves with old-context data — must be discarded
    resolveSlow({ items: [{ id: 99 }], total: 3, page: 2, size: 12 });
    await morePromise;
    await flushPromises();
    expect(wrapper.vm.items).toEqual([{ id: 1 }]);   // reset list, no stale append
    expect(wrapper.vm.loadingMore).toBe(false);
  });
});
