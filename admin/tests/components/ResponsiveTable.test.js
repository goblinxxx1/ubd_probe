import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const columns = [{ prop: "name", label: "Назва" }, { label: "Дії?", slot: "flag" }];
const rows = [{ id: 1, name: "Alpha", flag: true }];

function mountRT(mobile) {
  window.matchMedia = vi.fn(() => ({ matches: mobile, addEventListener() {}, removeEventListener() {} }));
  return mount(ResponsiveTable, {
    props: { columns, rows },
    slots: {
      "col-flag": '<template #col-flag="{ row }"><b class="flag">{{ row.flag ? "yes" : "no" }}</b></template>',
      actions: '<template #actions="{ row }"><button class="act">del {{ row.id }}</button></template>',
    },
    global: { plugins: [ElementPlus] },
  });
}

describe("ResponsiveTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders el-table on desktop", () => {
    const w = mountRT(false);
    expect(w.find(".el-table").exists()).toBe(true);
    expect(w.find(".rt-cards").exists()).toBe(false);
  });

  it("renders card stack with labels + slots on mobile", () => {
    const w = mountRT(true);
    expect(w.find(".rt-cards").exists()).toBe(true);
    expect(w.find(".el-table").exists()).toBe(false);
    expect(w.text()).toContain("Назва");
    expect(w.find(".flag").text()).toBe("yes");
    expect(w.find(".act").text()).toContain("del 1");
  });

  it("shows empty state on mobile with no rows", () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const w = mount(ResponsiveTable, { props: { columns, rows: [] }, global: { plugins: [ElementPlus] } });
    expect(w.find(".rt-empty").exists()).toBe(true);
  });
});
