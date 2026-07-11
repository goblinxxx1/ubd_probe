import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([{ id: 1, name: "УБД", slug: "ubd" }])),
  listOffer: vi.fn(() => Promise.resolve([{ id: 2, name: "Розваги", slug: "rozvahy" }])),
}));

import { useDictionaries } from "@/composables/useDictionaries";
import { listTarget, listOffer } from "@/api/categories";

describe("useDictionaries", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads both lists once and caches", async () => {
    const d = useDictionaries();
    await d.load();
    await d.load();
    expect(listTarget).toHaveBeenCalledTimes(1);
    expect(listOffer).toHaveBeenCalledTimes(1);
    expect(d.targetCategories.value[0].slug).toBe("ubd");
    expect(d.offerCategories.value[0].slug).toBe("rozvahy");
  });
});
