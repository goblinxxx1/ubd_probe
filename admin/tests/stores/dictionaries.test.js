import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
}));

import { useDictionariesStore } from "@/stores/dictionaries";
import { listTarget, listOffer } from "@/api/categories";

describe("dictionaries store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("load fetches both lists once", async () => {
    const store = useDictionariesStore();
    await store.load();
    await store.load();
    expect(listTarget).toHaveBeenCalledTimes(1);
    expect(listOffer).toHaveBeenCalledTimes(1);
    expect(store.targetCategories[0].slug).toBe("ubd");
    expect(store.offerCategories[0].slug).toBe("rozvahy");
    expect(store.loaded).toBe(true);
  });

  it("reload forces a refetch", async () => {
    const store = useDictionariesStore();
    await store.load();
    await store.reload();
    expect(listTarget).toHaveBeenCalledTimes(2);
  });
});
