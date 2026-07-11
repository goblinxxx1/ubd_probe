import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const client = { get: vi.fn(() => Promise.resolve({ data: "OK" })) };
  return { default: client };
});

import client from "@/api/client";
import * as offers from "@/api/offers";
import * as categories from "@/api/categories";
import { extractError } from "@/utils/errors";

beforeEach(() => vi.clearAllMocks());

describe("offers api", () => {
  it("list passes params", async () => {
    await offers.list({ type: "discount", page: 2, size: 12 });
    expect(client.get).toHaveBeenCalledWith("/offers", { params: { type: "discount", page: 2, size: 12 } });
  });
  it("get fetches by id", async () => {
    await offers.get(7);
    expect(client.get).toHaveBeenCalledWith("/offers/7");
  });
});

describe("categories api", () => {
  it("hits the open dictionary endpoints", async () => {
    await categories.listTarget();
    await categories.listOffer();
    expect(client.get).toHaveBeenCalledWith("/target-categories");
    expect(client.get).toHaveBeenCalledWith("/offer-categories");
  });
});

describe("extractError", () => {
  it("prefers detail, then message, then fallback", () => {
    expect(extractError({ response: { data: { detail: "Ой" } } })).toBe("Ой");
    expect(extractError({ message: "Network Error" })).toBe("Network Error");
    expect(extractError({})).toBe("Не вдалося завантажити. Спробуйте пізніше");
  });
});
