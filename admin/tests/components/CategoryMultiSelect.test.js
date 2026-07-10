import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import CategoryMultiSelect from "@/components/CategoryMultiSelect.vue";

describe("CategoryMultiSelect", () => {
  it("emits update:modelValue when selection changes", async () => {
    const wrapper = mount(CategoryMultiSelect, {
      props: { modelValue: [], options: [{ id: 1, name: "УБД" }] },
      global: { plugins: [ElementPlus] },
    });
    wrapper.vm.$emit("update:modelValue", [1]);
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted()["update:modelValue"][0]).toEqual([[1]]);
  });
});
