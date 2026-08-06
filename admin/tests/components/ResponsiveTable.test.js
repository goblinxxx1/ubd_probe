import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
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

  it("renders el-table on desktop", async () => {
    const w = mountRT(false);
    await flushPromises();
    await w.vm.$nextTick();
    expect(w.find(".el-table").exists()).toBe(true);
    expect(w.find(".rt-cards").exists()).toBe(false);
    expect(w.find(".flag").text()).toBe("yes");
    expect(w.find(".act").text()).toContain("del 1");
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

describe("ResponsiveTable selection", () => {
  const cols = [{ prop: "name", label: "Назва" }];
  const data = [{ id: 1, name: "Alpha" }, { id: 2, name: "Beta" }];

  it("renders a selection column on desktop when selectable", async () => {
    window.matchMedia = vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const w = mount(ResponsiveTable, {
      props: { columns: cols, rows: data, selectable: true },
      global: { plugins: [ElementPlus] },
    });
    await flushPromises();
    await w.vm.$nextTick();
    expect(w.find(".el-table-column--selection").exists()).toBe(true);
  });

  it("has no selection column when not selectable", async () => {
    window.matchMedia = vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const w = mount(ResponsiveTable, {
      props: { columns: cols, rows: data },
      global: { plugins: [ElementPlus] },
    });
    await flushPromises();
    await w.vm.$nextTick();
    expect(w.find(".el-table-column--selection").exists()).toBe(false);
  });

  it("emits selection-change with picked rows on mobile", async () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const w = mount(ResponsiveTable, {
      props: { columns: cols, rows: data, selectable: true },
      global: { plugins: [ElementPlus] },
    });
    const boxes = w.findAll(".rt-select input[type=checkbox]");
    expect(boxes.length).toBe(2);
    await boxes[1].setValue(true);
    const ev = w.emitted("selection-change");
    expect(ev).toBeTruthy();
    expect(ev.at(-1)[0]).toEqual([{ id: 2, name: "Beta" }]);
  });
});
