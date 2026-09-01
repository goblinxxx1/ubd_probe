import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import BlocklistView from "@/views/BlocklistView.vue";

vi.mock("@/api/blocklist", () => ({
  list: vi.fn(() => Promise.resolve([
    { id: 1, host: "media.example", status: "approved",
      sample_urls: ["https://media.example/a", "javascript:alert(1)"] },
  ])),
  unblock: vi.fn(() => Promise.resolve({})),
  create: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as blocklist from "@/api/blocklist";

describe("BlocklistView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the approved blocklist on mount", async () => {
    mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(blocklist.list).toHaveBeenCalled();
  });

  it("paginates with a bar above and below", async () => {
    blocklist.list.mockResolvedValueOnce(
      Array.from({ length: 25 }, (_, i) => ({ id: i + 1, host: `h${i}.example`, status: "approved", sample_urls: [] })),
    );
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "ElPagination" }).length).toBe(2);
    expect(wrapper.vm.pageItems.length).toBe(20);
    wrapper.vm.setPage(2);
    await flushPromises();
    expect(wrapper.vm.pageItems.length).toBe(5);
  });

  it("unblock calls the API and reloads", async () => {
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onUnblock(1);
    await flushPromises();
    expect(blocklist.unblock).toHaveBeenCalledWith(1);
    expect(blocklist.list).toHaveBeenCalledTimes(2);
  });

  it("renders http sample_urls as safe links", async () => {
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const link = wrapper.find('a[href="https://media.example/a"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes("target")).toBe("_blank");
  });

  it("does not render a non-http sample as a live link", async () => {
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(wrapper.text()).toContain("javascript:alert(1)");
    expect(wrapper.find('a[href="javascript:alert(1)"]').exists()).toBe(false);
  });

  it("adds a host to the blocklist and reloads", async () => {
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.newHost = "veteran.com.ua";
    await wrapper.vm.onAdd();
    await flushPromises();
    expect(blocklist.create).toHaveBeenCalledWith("veteran.com.ua");
    expect(wrapper.vm.newHost).toBe("");
    expect(blocklist.list).toHaveBeenCalledTimes(2);
  });

  it("ignores an empty add", async () => {
    const wrapper = mount(BlocklistView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.newHost = "   ";
    await wrapper.vm.onAdd();
    await flushPromises();
    expect(blocklist.create).not.toHaveBeenCalled();
  });
});
