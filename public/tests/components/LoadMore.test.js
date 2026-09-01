import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import LoadMore from "@/components/LoadMore.vue";

describe("LoadMore", () => {
  it("renders nothing when there is no more to load", () => {
    const w = mount(LoadMore, { props: { hasMore: false, shown: 12, total: 12 } });
    expect(w.find(".loadmore__btn").exists()).toBe(false);
  });

  it("emits load on click and shows progress", async () => {
    const w = mount(LoadMore, { props: { hasMore: true, loading: false, shown: 12, total: 40 } });
    expect(w.get(".loadmore__meta").text()).toContain("12");
    expect(w.get(".loadmore__meta").text()).toContain("40");
    await w.get(".loadmore__btn").trigger("click");
    expect(w.emitted().load).toBeTruthy();
  });

  it("disables the button while loading", () => {
    const w = mount(LoadMore, { props: { hasMore: true, loading: true, shown: 12, total: 40 } });
    expect(w.get(".loadmore__btn").attributes("disabled")).toBeDefined();
  });
});
