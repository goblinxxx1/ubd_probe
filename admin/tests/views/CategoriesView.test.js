import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import ElementPlus from "element-plus";
import CategoriesView from "@/views/CategoriesView.vue";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
  createTarget: vi.fn(() => Promise.resolve({})),
  updateTarget: vi.fn(() => Promise.resolve({})),
  removeTarget: vi.fn(() => Promise.resolve({})),
  createOffer: vi.fn(() => Promise.resolve({})),
  updateOffer: vi.fn(() => Promise.resolve({})),
  removeOffer: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as categories from "@/api/categories";

describe("CategoriesView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("creates a target category and reloads the dictionary", async () => {
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.save("target", { name: "Ветеран", slug: "veteran" });
    await flushPromises();
    expect(categories.createTarget).toHaveBeenCalledWith({ name: "Ветеран", slug: "veteran" });
    // dictionaries.reload re-fetches both lists (once on mount + once after save)
    expect(categories.listTarget).toHaveBeenCalledTimes(2);
  });

  it("deletes an offer category", async () => {
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.remove("offer", 2);
    await flushPromises();
    expect(categories.removeOffer).toHaveBeenCalledWith(2);
  });

  it("updates a target category via startEdit + save", async () => {
    const wrapper = mount(CategoriesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.save("target", { name: "УБД+", slug: "ubd" }, 1);
    await flushPromises();
    expect(categories.updateTarget).toHaveBeenCalledWith(1, { name: "УБД+", slug: "ubd" });
  });
});
