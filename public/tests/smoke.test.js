import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import App from "@/App.vue";
import router from "@/router";

vi.mock("@/api/offers", () => ({
  list: vi.fn(() => Promise.resolve({ items: [], total: 0, page: 1, size: 12 })),
  get: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/api/categories", () => ({
  listTarget: vi.fn(() => Promise.resolve([])),
  listOffer: vi.fn(() => Promise.resolve([])),
}));

describe("App", () => {
  beforeEach(() => router.push("/"));

  it("renders header and footer around the router view", async () => {
    await router.isReady();
    const wrapper = mount(App, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Знижки для УБД");
    expect(wrapper.text()).toContain("учасників бойових дій");
  });
});
