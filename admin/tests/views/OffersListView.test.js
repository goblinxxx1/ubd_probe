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
  restore: vi.fn(() => Promise.resolve({})),
  blockHost: vi.fn(() => Promise.resolve({ host: "h", status: "approved" })),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn() },
    ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
  };
});
import * as offers from "@/api/offers";
import { useModerationStore } from "@/stores/moderation";

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
    expect(offers.list).toHaveBeenCalledWith({ status: "published", page: 1, size: 20 });
  });

  it("switching to the moderation tab reloads with pending_review status", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    wrapper.vm.tab = "pending_review";
    await wrapper.vm.applyFilters({});
    await flushPromises();
    expect(offers.list).toHaveBeenLastCalledWith({ status: "pending_review", page: 1, size: 20 });
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
    // mount load + reload after the action + moderation badge refresh
    expect(offers.list).toHaveBeenCalledTimes(3);
  });

  it("forces status when fixedStatus is set", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    mount(OffersListView, { props: { fixedStatus: "pending_review" }, global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ status: "pending_review", page: 1, size: 20 });
  });

  it("shows a discount-count tag when a row has multiple discounts", async () => {
    offers.list.mockResolvedValueOnce({
      items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "pending_review", valid_until: null,
        discounts: [{ label: "a", discount_type: "percent", discount_value: 10 }, { label: "b", discount_type: "percent", discount_value: 20 }] }],
      total: 1,
    });
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(wrapper.text()).toContain("2 знижки");
  });

  it("switching to the rejected tab reloads with rejected status", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    wrapper.vm.tab = "rejected";
    await wrapper.vm.applyFilters({});
    await flushPromises();
    expect(offers.list).toHaveBeenLastCalledWith({ status: "rejected", page: 1, size: 20 });
  });

  it("restore calls the API and reloads", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onRestore(1);
    await flushPromises();
    expect(offers.restore).toHaveBeenCalledWith(1);
    // mount load + reload after the action + moderation badge refresh
    expect(offers.list).toHaveBeenCalledTimes(3);
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

  it("block-host calls the API after confirm and reloads", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onBlockHost(1);
    await flushPromises();
    expect(offers.blockHost).toHaveBeenCalledWith(1);
  });

  it("block-host does nothing when confirm is cancelled", async () => {
    const { ElMessageBox } = await import("element-plus");
    ElMessageBox.confirm.mockRejectedValueOnce("cancel");
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onBlockHost(1);
    await flushPromises();
    expect(offers.blockHost).not.toHaveBeenCalled();
  });

  it("publish refreshes the moderation badge count", async () => {
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    const store = useModerationStore();
    const spy = vi.spyOn(store, "refresh");
    await wrapper.vm.onPublish(1);
    await flushPromises();
    expect(spy).toHaveBeenCalled();
  });

  it("renders a pagination bar both above and below the table", async () => {
    offers.list.mockResolvedValueOnce({
      items: [{ id: 1, title: "T", provider: "P", type: "discount", status: "published", valid_until: null }],
      total: 40,
    });
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "ElPagination" }).length).toBe(2);
  });

  it("initialises the tab from the URL query", async () => {
    const router = makeRouter();
    router.push("/?tab=rejected");
    await router.isReady();
    mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    expect(offers.list).toHaveBeenCalledWith({ status: "rejected", page: 1, size: 20 });
  });

  it("edit navigates carrying from + tab query", async () => {
    const router = makeRouter();
    const spy = vi.spyOn(router, "push");
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    wrapper.vm.tab = "pending_review";
    wrapper.vm.edit(5);
    expect(spy).toHaveBeenCalledWith({
      name: "offer-edit", params: { id: 5 },
      query: { from: "offers", tab: "pending_review" },
    });
  });

  it("preview opens the article_url in a new window", async () => {
    const spy = vi.spyOn(window, "open").mockImplementation(() => {});
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    wrapper.vm.preview({ article_url: "https://promo.example/x", site_url: "https://site.example" });
    expect(spy).toHaveBeenCalledWith("https://promo.example/x", "_blank", "noopener");
    spy.mockRestore();
  });

  it("preview falls back to site_url when no article_url", async () => {
    const spy = vi.spyOn(window, "open").mockImplementation(() => {});
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, { global: { plugins: [router, ElementPlus] } });
    await flushPromises();
    wrapper.vm.preview({ article_url: null, site_url: "https://site.example" });
    expect(spy).toHaveBeenCalledWith("https://site.example", "_blank", "noopener");
    spy.mockRestore();
  });

  it("renders confidence tag + signal chips + inline city/category tags for a pending row", async () => {
    offers.list.mockResolvedValueOnce({
      items: [{
        id: 1, title: "T", provider: "P", type: "discount", status: "pending_review",
        valid_until: null, discount_type: "percent", discount_value: 20,
        locations: ["Київ", "Львів"], offer_categories: [{ id: 3, name: "Медицина" }],
        confidence: { tier: "low", host: "noisy.ua", host_published: 0, host_rejected: 2,
                      signals: ["noisy_host", "no_category"] },
      }],
      total: 1,
    });
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(OffersListView, {
      props: { fixedStatus: "pending_review" },
      global: { plugins: [router, ElementPlus] },
    });
    await flushPromises();
    const txt = wrapper.text();
    expect(txt).toContain("Низька");          // confidence tier label
    expect(txt).toContain("шумний хост");     // signal chip
    expect(txt).toContain("Київ");            // inline city
    expect(txt).toContain("Медицина");        // inline category
    expect(txt).toContain("−20%");            // inline discount
  });
});
