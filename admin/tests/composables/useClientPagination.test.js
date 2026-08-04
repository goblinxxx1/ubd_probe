import { describe, it, expect } from "vitest";
import { ref, nextTick } from "vue";
import { useClientPagination } from "@/composables/useClientPagination";

describe("useClientPagination", () => {
  it("slices the source into pages", () => {
    const src = ref(Array.from({ length: 45 }, (_, i) => i));
    const { size, total, pageItems, setPage } = useClientPagination(src, 20);
    expect(size).toBe(20);
    expect(total.value).toBe(45);
    expect(pageItems.value).toEqual(src.value.slice(0, 20));
    setPage(2);
    expect(pageItems.value).toEqual(src.value.slice(20, 40));
    setPage(3);
    expect(pageItems.value).toEqual(src.value.slice(40, 45));
  });

  it("resets to page 1 when the source is replaced (reload/filter change)", async () => {
    const src = ref([1, 2, 3, 4, 5]);
    const { page, setPage } = useClientPagination(src, 2);
    setPage(3);
    expect(page.value).toBe(3);
    src.value = [9, 8, 7];
    await nextTick();
    expect(page.value).toBe(1);
  });
});
