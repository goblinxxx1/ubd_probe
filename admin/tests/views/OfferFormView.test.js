import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import OfferFormView from "@/views/OfferFormView.vue";

vi.mock("@/api/offers", () => ({
  get: vi.fn(() => Promise.resolve({ id: 5, type: "discount", title: "Old", provider: "P", target_categories: [], offer_categories: [] })),
  create: vi.fn(() => Promise.resolve({ id: 9 })),
  update: vi.fn(() => Promise.resolve({ id: 5 })),
}));
vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([])),
  listOffer: vi.fn(() => Promise.resolve([])),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});
import * as offers from "@/api/offers";

function mountView(path, routeName, params = {}) {
  const stub = { template: "<div/>" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/offers/new", name: "offer-new", component: OfferFormView },
      { path: "/offers/:id/edit", name: "offer-edit", component: OfferFormView },
    ],
  });
  router.push(path);
  return router.isReady().then(() => mount(OfferFormView, { global: { plugins: [router, ElementPlus] } }));
}

describe("OfferFormView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("creates a new offer on submit", async () => {
    const wrapper = await mountView("/offers/new");
    await flushPromises();
    wrapper.vm.onSubmit({ title: "New", type: "event", provider: "P" });
    await flushPromises();
    expect(offers.create).toHaveBeenCalledWith({ title: "New", type: "event", provider: "P" });
  });

  it("loads and updates an existing offer", async () => {
    const wrapper = await mountView("/offers/5/edit");
    await flushPromises();
    expect(offers.get).toHaveBeenCalledWith("5");
    wrapper.vm.onSubmit({ title: "Upd", type: "discount", provider: "P" });
    await flushPromises();
    expect(offers.update).toHaveBeenCalledWith("5", { title: "Upd", type: "discount", provider: "P" });
  });
});
