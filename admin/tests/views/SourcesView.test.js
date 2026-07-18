import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import SourcesView from "@/views/SourcesView.vue";

vi.mock("@/api/sources", () => ({
  list: vi.fn(() => Promise.resolve([{ id: 1, name: "S", type: "telegram", url_or_handle: "@s", is_active: true }])),
  create: vi.fn(() => Promise.resolve({})),
  update: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as sources from "@/api/sources";

describe("SourcesView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads sources on mount", async () => {
    mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(sources.list).toHaveBeenCalled();
  });

  it("creates a source via the dialog", async () => {
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.openCreate();
    Object.assign(wrapper.vm.form, { name: "New", type: "website", url_or_handle: "https://x", is_active: true });
    await wrapper.vm.save();
    await flushPromises();
    expect(sources.create).toHaveBeenCalledWith({ name: "New", type: "website", url_or_handle: "https://x", is_active: true });
    expect(sources.list).toHaveBeenCalledTimes(2);
  });

  it("deletes a source", async () => {
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onDelete(1);
    await flushPromises();
    expect(sources.remove).toHaveBeenCalledWith(1);
  });

  it("renders url_or_handle as a link for website sources, plain text otherwise", async () => {
    sources.list.mockResolvedValueOnce([
      { id: 1, name: "W", type: "website", url_or_handle: "https://site.example", is_active: true },
      { id: 2, name: "T", type: "telegram", url_or_handle: "@chan", is_active: true },
      { id: 3, name: "X", type: "website", url_or_handle: "javascript:alert(1)", is_active: true },
    ]);
    const wrapper = mount(SourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://site.example"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
    expect(wrapper.text()).toContain("@chan");
    expect(wrapper.find('a[href="@chan"]').exists()).toBe(false);
    expect(wrapper.find('a[href="javascript:alert(1)"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("javascript:alert(1)");
  });
});
