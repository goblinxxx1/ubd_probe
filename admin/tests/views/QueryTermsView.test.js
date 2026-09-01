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
  bulk: vi.fn(() => Promise.resolve({ done: [1, 2], failed: [] })),
}));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
    ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
  };
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
    const btn = wrapper.findAll("button")
      .filter((b) => !b.element.closest(".bulkbar"))
      .find((b) => b.text().includes("Повернути в кандидати"));
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
    const btn = wrapper.findAll("button")
      .filter((b) => !b.element.closest(".bulkbar"))
      .find((b) => b.text().includes("Повернути в кандидати"));
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
    // unprotected row surfaces the «Закріпити» control
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels).toContain("Закріпити");
    await wrapper.vm.onProtect(3);
    await flushPromises();
    expect(terms.protect).toHaveBeenCalledWith(3);
    expect(terms.list).toHaveBeenCalledTimes(3);
  });

  it("renders «Відкріпити» on a protected row; onUnprotect calls the API and reloads", async () => {
    terms.list.mockResolvedValue([
      { id: 4, term: "ручний терм", z: 0, support: 0, status: "approved", protected: true },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "approved";
    await wrapper.vm.load();
    await flushPromises();
    // protected row surfaces «Відкріпити»
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels).toContain("Відкріпити");
    await wrapper.vm.onUnprotect(4);
    await flushPromises();
    expect(terms.unprotect).toHaveBeenCalledWith(4);
    expect(terms.list).toHaveBeenCalledTimes(3);
  });

  // --- масові дії ---
  const bulkLabels = (wrapper) =>
    wrapper.find(".bulkbar").findAll("button").map((b) => b.text());

  it("pending tab shows bulk approve + reject buttons", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const labels = bulkLabels(wrapper);
    expect(labels).toContain("Затвердити вибрані");
    expect(labels).toContain("Відхилити вибрані");
    expect(labels).toContain("Закріпити вибрані");
    expect(labels).toContain("Відкріпити вибрані");
  });

  it("approved/rejected tabs show a bulk «Повернути в кандидати» (no bulk approve)", async () => {
    terms.list.mockResolvedValue([
      { id: 7, term: "евакуатор", z: 1.2, support: 5, status: "approved" },
    ]);
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    wrapper.vm.status = "approved";
    await wrapper.vm.load();
    await flushPromises();
    const labels = bulkLabels(wrapper);
    expect(labels).toContain("Повернути в кандидати");
    expect(labels).not.toContain("Затвердити вибрані");
  });

  it("bulk buttons are disabled with an empty selection", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    const disabled = wrapper.find(".bulkbar").findAll("button")
      .every((b) => b.attributes("disabled") !== undefined);
    expect(disabled).toBe(true);
  });

  it("runBulk posts selected ids + action and reloads", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.selected = [{ id: 1 }, { id: 2 }];
    await wrapper.vm.runBulk("approve");
    await flushPromises();
    expect(terms.bulk).toHaveBeenCalledWith([1, 2], "approve");
    expect(terms.list).toHaveBeenCalledTimes(2);   // mount + post-bulk reload
  });

  it("runBulk with an empty selection is a no-op", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.selected = [];
    await wrapper.vm.runBulk("reject", "confirm?");
    await flushPromises();
    expect(terms.bulk).not.toHaveBeenCalled();
  });

  it("clicking bulk «Затвердити вибрані» sends the approve action", async () => {
    const wrapper = mount(QueryTermsView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    wrapper.vm.selected = [{ id: 1 }];
    await flushPromises();
    const btn = wrapper.find(".bulkbar").findAll("button")
      .find((b) => b.text() === "Затвердити вибрані");
    await btn.trigger("click");
    await flushPromises();
    expect(terms.bulk).toHaveBeenCalledWith([1], "approve");
  });
});
