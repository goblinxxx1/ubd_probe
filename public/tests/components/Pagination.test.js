import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import Pagination from "@/components/Pagination.vue";

describe("Pagination", () => {
  it("renders nothing for a single page", () => {
    const w = mount(Pagination, { props: { total: 10, size: 12, page: 1 } });
    expect(w.find("button").exists()).toBe(false);
  });

  it("emits the next page", async () => {
    const w = mount(Pagination, { props: { total: 40, size: 12, page: 1 } });
    await w.get("[data-test=next]").trigger("click");
    expect(w.emitted().change[0]).toEqual([2]);
  });

  it("disables prev on the first page and next on the last", () => {
    const first = mount(Pagination, { props: { total: 40, size: 12, page: 1 } });
    expect(first.get("[data-test=prev]").attributes("disabled")).toBeDefined();
    const last = mount(Pagination, { props: { total: 40, size: 12, page: 4 } });
    expect(last.get("[data-test=next]").attributes("disabled")).toBeDefined();
  });
});
