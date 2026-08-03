import { describe, it, expect, vi, beforeEach } from "vitest";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/api/offers", () => ({ list: vi.fn(() => Promise.resolve({ total: 7 })) }));
import * as offers from "@/api/offers";
import { useModerationStore } from "@/stores/moderation";

describe("moderation store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("refresh loads the pending_review total", async () => {
    const s = useModerationStore();
    expect(s.pendingCount).toBe(0);
    await s.refresh();
    expect(offers.list).toHaveBeenCalledWith({ status: "pending_review", size: 1 });
    expect(s.pendingCount).toBe(7);
  });

  it("refresh swallows errors and keeps the prior count", async () => {
    offers.list.mockRejectedValueOnce(new Error("x"));
    const s = useModerationStore();
    await s.refresh();
    expect(s.pendingCount).toBe(0);
  });
});
