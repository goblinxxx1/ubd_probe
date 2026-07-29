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

  it("shows publish only for a non-published existing offer", () => {
    const base = { global: { plugins: [ElementPlus] } };
    const pub = mount(OfferForm, { props: { initial: { id: 5, status: "published", target_categories: [], offer_categories: [] } }, ...base });
    expect(pub.vm.canPublish).toBe(false);
    const pend = mount(OfferForm, { props: { initial: { id: 5, status: "pending_review", target_categories: [], offer_categories: [] } }, ...base });
    expect(pend.vm.canPublish).toBe(true);
    const fresh = mount(OfferForm, { props: { initial: null }, ...base });
    expect(fresh.vm.canPublish).toBeFalsy();
  });

  it("emits submit-publish with a built payload when valid", () => {
    const wrapper = mount(OfferForm, {
      props: { initial: { id: 5, status: "pending_review", target_categories: [], offer_categories: [] } },
      global: { plugins: [ElementPlus] },
    });
    Object.assign(wrapper.vm.form, { type: "event", title: "Подія", provider: "Орг" });
    wrapper.vm.submitPublish();
    expect(wrapper.emitted()["submit-publish"][0][0].title).toBe("Подія");
  });

  it("seeds locations from the initial offer and includes them in the payload", () => {
    const wrapper = mount(OfferForm, {
      props: { initial: { type: "discount", title: "T", provider: "P",
                          locations: ["Київ", "Львів"], target_categories: [], offer_categories: [] } },
      global: { plugins: [ElementPlus] },
    });
    expect(wrapper.vm.form.locations).toEqual(["Київ", "Львів"]);
    Object.assign(wrapper.vm.form, { discount_type: "percent", discount_value: 10 });
    wrapper.vm.submit();
    expect(wrapper.emitted().submit[0][0].locations).toEqual(["Київ", "Львів"]);
  });

  it("seeds discounts from the initial offer and includes them in the payload", () => {
    const wrapper = mount(OfferForm, {
      props: { initial: { type: "discount", title: "T", provider: "P",
                          discounts: [{ label: "МВС", discount_type: "percent", discount_value: 10 }],
                          target_categories: [], offer_categories: [] } },
      global: { plugins: [ElementPlus] },
    });
    expect(wrapper.vm.form.discounts).toEqual([{ label: "МВС", discount_type: "percent", discount_value: 10 }]);
    Object.assign(wrapper.vm.form, { discount_type: "percent", discount_value: 10 });
    wrapper.vm.submit();
    expect(wrapper.emitted().submit[0][0].discounts).toEqual([{ label: "МВС", discount_type: "percent", discount_value: 10 }]);
  });

  it("defaults discounts to an empty array for a new offer", () => {
    const wrapper = mount(OfferForm, { props: { initial: null }, global: { plugins: [ElementPlus] } });
    expect(wrapper.vm.form.discounts).toEqual([]);
  });

  it("addDiscount appends a default row and removeDiscount removes it by index", () => {
    const wrapper = mount(OfferForm, { props: { initial: null }, global: { plugins: [ElementPlus] } });
    wrapper.vm.addDiscount();
    expect(wrapper.vm.form.discounts).toEqual([{ label: "", discount_type: "percent", discount_value: null }]);
    wrapper.vm.removeDiscount(0);
    expect(wrapper.vm.form.discounts).toEqual([]);
  });
});
