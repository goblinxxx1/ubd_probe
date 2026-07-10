import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import DataTableToolbar from "@/components/DataTableToolbar.vue";

describe("DataTableToolbar", () => {
  it("emits search with the query on button click", async () => {
    const wrapper = mount(DataTableToolbar, { global: { plugins: [ElementPlus] } });
    wrapper.vm.q = "коло";
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted().search[0]).toEqual(["коло"]);
  });
});
