import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import { useOffers } from "@/composables/useOffers";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [{ id: 1 }], total: 1, page: 1, size: 12 })),
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
});
