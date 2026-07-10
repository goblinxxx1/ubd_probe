import { describe, it, expect, vi } from "vitest";
import { useApiList } from "@/composables/useApiList";

describe("useApiList", () => {
  it("loads a paged result", async () => {
    const loader = vi.fn(() => Promise.resolve({ items: [{ id: 1 }], total: 42 }));
    const list = useApiList(loader, { status: "" });
    await list.load();
    expect(loader).toHaveBeenCalledWith({ status: "", page: 1, size: 20 });
    expect(list.items.value).toEqual([{ id: 1 }]);
    expect(list.total.value).toBe(42);
  });

  it("supports plain array results", async () => {
    const loader = vi.fn(() => Promise.resolve([{ id: 1 }, { id: 2 }]));
    const list = useApiList(loader);
    await list.load();
    expect(list.items.value.length).toBe(2);
    expect(list.total.value).toBe(2);
  });

  it("applyFilters resets page and merges filters", async () => {
    const loader = vi.fn(() => Promise.resolve([]));
    const list = useApiList(loader, { status: "" });
    list.page.value = 3;
    await list.applyFilters({ status: "published" });
    expect(list.page.value).toBe(1);
    expect(loader).toHaveBeenLastCalledWith({ status: "published", page: 1, size: 20 });
  });
});
