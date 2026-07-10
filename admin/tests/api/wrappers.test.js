import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const client = {
    get: vi.fn(() => Promise.resolve({ data: "GET" })),
    post: vi.fn(() => Promise.resolve({ data: "POST" })),
    patch: vi.fn(() => Promise.resolve({ data: "PATCH" })),
    delete: vi.fn(() => Promise.resolve({ data: "DELETE" })),
  };
  return { default: client };
});

import client from "@/api/client";
import * as offers from "@/api/offers";
import * as sources from "@/api/sources";
import * as suggested from "@/api/suggestedSources";
import * as categories from "@/api/categories";
import * as users from "@/api/users";

beforeEach(() => vi.clearAllMocks());

describe("offers api", () => {
  it("list passes params", async () => {
    const data = await offers.list({ status: "published", page: 2 });
    expect(client.get).toHaveBeenCalledWith("/admin/offers", { params: { status: "published", page: 2 } });
    expect(data).toBe("GET");
  });
  it("publish posts to the publish endpoint", async () => {
    await offers.publish(7);
    expect(client.post).toHaveBeenCalledWith("/admin/offers/7/publish");
  });
  it("remove deletes by id", async () => {
    await offers.remove(3);
    expect(client.delete).toHaveBeenCalledWith("/admin/offers/3");
  });
});

describe("suggested sources api", () => {
  it("approve posts to approve endpoint", async () => {
    await suggested.approve(5);
    expect(client.post).toHaveBeenCalledWith("/admin/suggested-sources/5/approve");
  });
});

describe("categories api", () => {
  it("listTarget hits the open endpoint", async () => {
    await categories.listTarget();
    expect(client.get).toHaveBeenCalledWith("/target-categories");
  });
  it("createOffer posts to admin offer-categories", async () => {
    await categories.createOffer({ name: "X", slug: "x" });
    expect(client.post).toHaveBeenCalledWith("/admin/offer-categories", { name: "X", slug: "x" });
  });
});

describe("users api", () => {
  it("remove deletes by id", async () => {
    await users.remove(9);
    expect(client.delete).toHaveBeenCalledWith("/admin/users/9");
  });
});

describe("sources api", () => {
  it("update patches by id", async () => {
    await sources.update(4, { is_active: false });
    expect(client.patch).toHaveBeenCalledWith("/admin/sources/4", { is_active: false });
  });
});
