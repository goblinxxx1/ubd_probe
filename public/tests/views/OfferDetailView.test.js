import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferDetailView from "@/views/OfferDetailView.vue";

vi.mock("@/api/offers", () => ({ get: vi.fn() }));
import * as offers from "@/api/offers";

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: { template: "<div/>" } },
      { path: "/offers/:id", name: "offer", component: OfferDetailView },
    ],
  });
}

async function mountAt(id) {
  const router = makeRouter();
  router.push(`/offers/${id}`);
  await router.isReady();
  const wrapper = mount(OfferDetailView, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("OfferDetailView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads and renders an offer", async () => {
    offers.get.mockResolvedValue({
      id: 5, type: "discount", discount_type: "percent", discount_value: 30,
      title: "Знижка 30%", provider: "Кафе", description: "Опис", location: "Київ",
      valid_from: "2026-07-01", valid_until: "2026-08-01", contacts: "0501112233",
      image_url: null, target_categories: [{ id: 1, name: "УБД" }], offer_categories: [{ id: 2, name: "Кафе" }],
    });
    const w = await mountAt(5);
    expect(offers.get).toHaveBeenCalledWith("5");
    expect(w.text()).toContain("Знижка 30%");
    expect(w.text()).toContain("Кафе");
    expect(w.text()).toContain("0501112233");
    expect(w.text()).toContain("01.07.2026");
  });

  it("shows a not-found state when the offer is missing", async () => {
    offers.get.mockRejectedValue({ response: { status: 404 } });
    const w = await mountAt(999);
    expect(w.vm.notFound).toBe(true);
    expect(w.text()).toContain("не знайдено");
  });
});
