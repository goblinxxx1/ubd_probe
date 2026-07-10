import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import SuggestedSourcesView from "@/views/SuggestedSourcesView.vue";

vi.mock("@/api/suggestedSources", () => ({
  list: vi.fn(() => Promise.resolve([
    { id: 3, name: "New TG", type: "telegram", url_or_handle: "@n", discovery_note: "нотатка", status: "pending" },
  ])),
  approve: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as suggested from "@/api/suggestedSources";

describe("SuggestedSourcesView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads pending suggestions on mount", async () => {
    mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(suggested.list).toHaveBeenCalledWith({ status: "pending" });
  });

  it("approve calls the API and reloads", async () => {
    const wrapper = mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onApprove(3);
    await flushPromises();
    expect(suggested.approve).toHaveBeenCalledWith(3);
    expect(suggested.list).toHaveBeenCalledTimes(2);
  });

  it("reject calls the API", async () => {
    const wrapper = mount(SuggestedSourcesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onReject(3);
    await flushPromises();
    expect(suggested.reject).toHaveBeenCalledWith(3);
    expect(suggested.list).toHaveBeenCalledTimes(2);
  });
});
