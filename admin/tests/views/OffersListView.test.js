import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import OffersListView from "@/views/OffersListView.vue";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({
    items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "pending_review", valid_until: null }],
    total: 1,
  })),
  publish: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as offers from "@/api/offers";

function makeRouter() {
  const stub = { template: "<div/>" };
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/offers/new", name: "offer-new", component: stub },
      { path: "/offers/:id/edit", name: "offer-edit", component: stub },
    ],
  });
}

describe("OffersListView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads offers on mount with empty filters stripped", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ page: 1, size: 20 });
  });

  it("publish calls the API and reloads", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onPublish(1);
    await flushPromises();
    expect(offers.publish).toHaveBeenCalledWith(1);
    expect(offers.list).toHaveBeenCalledTimes(2);
  });

  it("forces status when fixedStatus is set", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersListView, { props: { fixedStatus: "pending_review" }, global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ status: "pending_review", page: 1, size: 20 });
  });

  it("renders a clickable source link when site_url is present", async () => {
    offers.list.mockResolvedValueOnce({
      items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "published", valid_until: null, site_url: "https://shop.example", article_url: null }],
      total: 1,
    });
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://shop.example"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toContain("noopener");
  });
});
