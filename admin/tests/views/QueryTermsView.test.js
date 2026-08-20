import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import QueryTermsView from "@/views/QueryTermsView.vue";

vi.mock("@/api/queryTerms", () => ({
  list: vi.fn(() => Promise.resolve([
    { id: 1, term: "манікюр", z: 1.02, support: 3, status: "pending" },
  ])),
  approve: vi.fn(() => Promise.resolve({})),
  reject: vi.fn(() => Promise.resolve({})),
  unreject: vi.fn(() => Promise.resolve({})),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as terms from "@/api/queryTerms";

describe("QueryTermsView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads pending candidates on mount", async () => {
    mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(terms.list).toHaveBeenCalledWith({ status: "pending" });
  });

  it("shows the support column as «Бізнес-сайтів» and no z column", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const headers = wrapper.findAll("th").map((th) => th.text());
    expect(headers).toContain("Бізнес-сайтів");
    expect(headers).not.toContain("z");
  });

  it("renders «Повернути в кандидати» on a rejected row and calls unreject", async () => {
    terms.list.mockResolvedValue([
      { id: 9, term: "грн", z: 0.8, support: 3, status: "rejected" },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "rejected";
    await wrapper.vm.load();
    await flushPromises();
    const btn = wrapper.findAll("button").find((b) => b.text().includes("Повернути в кандидати"));
    expect(btn).toBeTruthy();
    await btn.trigger("click");
    await flushPromises();
    expect(terms.unreject).toHaveBeenCalledWith(9);
    expect(terms.list).toHaveBeenLastCalledWith({ status: "rejected" });
  });

  it("onUnreject calls the API and reloads", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onUnreject(1);
    await flushPromises();
    expect(terms.unreject).toHaveBeenCalledWith(1);
    expect(terms.list).toHaveBeenCalledTimes(2);
  });
});
