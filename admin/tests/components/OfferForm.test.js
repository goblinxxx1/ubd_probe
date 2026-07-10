import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus, { ElMessage } from "element-plus";
import OfferForm from "@/components/OfferForm.vue";

vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});

describe("OfferForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("emits submit with a built payload when valid", async () => {
    const wrapper = mount(OfferForm, {
      props: { initial: null, targetCategories: [{ id: 1, name: "УБД" }], offerCategories: [{ id: 2, name: "Розваги" }] },
      global: { plugins: [ElementPlus] },
    });
    Object.assign(wrapper.vm.form, {
      type: "discount", title: "Знижка", provider: "Магазин",
      discount_type: "percent", discount_value: 20, target_category_ids: [1], offer_category_ids: [2],
    });
    wrapper.vm.submit();
    const payload = wrapper.emitted().submit[0][0];
    expect(payload.title).toBe("Знижка");
    expect(payload.discount_value).toBe(20);
    expect(payload.target_category_ids).toEqual([1]);
  });

  it("blocks submit and shows an error when invalid", () => {
    const wrapper = mount(OfferForm, { props: { initial: null }, global: { plugins: [ElementPlus] } });
    Object.assign(wrapper.vm.form, { type: "discount", title: "", provider: "" });
    wrapper.vm.submit();
    expect(ElMessage.error).toHaveBeenCalled();
    expect(wrapper.emitted().submit).toBeUndefined();
  });

  it("seeds the form from an initial offer (edit)", () => {
    const wrapper = mount(OfferForm, {
      props: {
        initial: { type: "event", title: "Подія", provider: "Музей", target_categories: [{ id: 3, name: "Ветеран" }], offer_categories: [] },
      },
      global: { plugins: [ElementPlus] },
    });
    expect(wrapper.vm.form.title).toBe("Подія");
    expect(wrapper.vm.form.target_category_ids).toEqual([3]);
  });
});
