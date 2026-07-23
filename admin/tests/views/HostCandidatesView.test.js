import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import HostCandidatesView from "@/views/HostCandidatesView.vue";

vi.mock("@/api/hostCandidates", () => ({
  list: vi.fn(() => Promise.resolve([
    { id: 1, host: "media.example", status: "pending", media_ratio: 0.9,
      aggregator_ratio: 0.1, support: 4, sample_urls: ["https://media.example/a"] },
  ])),
  approve: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as hosts from "@/api/hostCandidates";

describe("HostCandidatesView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads pending host candidates on mount", async () => {
    mount(HostCandidatesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(hosts.list).toHaveBeenCalledWith({ status: "pending" });
  });

  it("approve calls the API and reloads", async () => {
    const wrapper = mount(HostCandidatesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onApprove(1);
    await flushPromises();
    expect(hosts.approve).toHaveBeenCalledWith(1);
    expect(hosts.list).toHaveBeenCalledTimes(2);
  });

  it("reject calls the API and reloads", async () => {
    const wrapper = mount(HostCandidatesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onReject(1);
    await flushPromises();
    expect(hosts.reject).toHaveBeenCalledWith(1);
    expect(hosts.list).toHaveBeenCalledTimes(2);
  });

  it("renders sample_urls as links and shows media/aggregator ratios", async () => {
    const wrapper = mount(HostCandidatesView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(wrapper.text()).toContain("90%");
    expect(wrapper.text()).toContain("10%");
    const link = wrapper.find('a[href="https://media.example/a"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
  });
});
