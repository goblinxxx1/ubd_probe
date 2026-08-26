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
  toPending: vi.fn(() => Promise.resolve({})),
  manualAdd: vi.fn(() => Promise.resolve({})),
  protect: vi.fn(() => Promise.resolve({})),
  unprotect: vi.fn(() => Promise.resolve({})),
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

  it("renders «Повернути в кандидати» on an approved row and calls toPending", async () => {
    terms.list.mockResolvedValue([
      { id: 7, term: "евакуатор", z: 1.2, support: 5, status: "approved" },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "approved";
    await wrapper.vm.load();
    await flushPromises();
    const btn = wrapper.findAll("button").find((b) => b.text().includes("Повернути в кандидати"));
    expect(btn).toBeTruthy();
    await btn.trigger("click");
    await flushPromises();
    expect(terms.toPending).toHaveBeenCalledWith(7);
    expect(terms.list).toHaveBeenLastCalledWith({ status: "approved" });
  });

  it("onUnreject calls the API and reloads", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onUnreject(1);
    await flushPromises();
    expect(terms.unreject).toHaveBeenCalledWith(1);
    expect(terms.list).toHaveBeenCalledTimes(2);
  });

  it("manual add posts the term, clears the input and reloads (Задача 5C)", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.newTerm = "  Ручний Терм  ";
    await wrapper.vm.onManualAdd();
    await flushPromises();
    expect(terms.manualAdd).toHaveBeenCalledWith("Ручний Терм");
    expect(wrapper.vm.newTerm).toBe("");
    expect(terms.list).toHaveBeenCalledTimes(2);
  });

  it("blank manual add does not call the API", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.newTerm = "   ";
    await wrapper.vm.onManualAdd();
    await flushPromises();
    expect(terms.manualAdd).not.toHaveBeenCalled();
  });

  it("renders «Захистити» on an unprotected row; onProtect calls the API and reloads", async () => {
    terms.list.mockResolvedValue([
      { id: 3, term: "масаж", z: 1.0, support: 4, status: "approved", protected: false },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "approved";
    await wrapper.vm.load();
    await flushPromises();
    // unprotected row surfaces the «Захистити» control
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels).toContain("Захистити");
    await wrapper.vm.onProtect(3);
    await flushPromises();
    expect(terms.protect).toHaveBeenCalledWith(3);
    expect(terms.list).toHaveBeenCalledTimes(3);
  });

  it("renders «Зняти захист» on a protected row; onUnprotect calls the API and reloads", async () => {
    terms.list.mockResolvedValue([
      { id: 4, term: "ручний терм", z: 0, support: 0, status: "approved", protected: true },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "approved";
    await wrapper.vm.load();
    await flushPromises();
    // protected row surfaces «Зняти захист»
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels).toContain("Зняти захист");
    await wrapper.vm.onUnprotect(4);
    await flushPromises();
    expect(terms.unprotect).toHaveBeenCalledWith(4);
    expect(terms.list).toHaveBeenCalledTimes(3);
  });
});
