import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import OfferCard from "@/components/OfferCard.vue";

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: "/", name: "offers", component: { template: "<div/>" } },
    { path: "/offers/:id", name: "offer", component: { template: "<div/>" } },
  ],
});

function mountCard(offer) {
  return mount(OfferCard, { props: { offer }, global: { plugins: [router] } });
}

describe("OfferCard", () => {
  it("uses the placeholder photo when image_url is empty and shows fields", () => {
    const w = mountCard({
      id: 3, type: "discount", discount_type: "free", title: "на все меню",
      provider: "Музей", description: "", location: "Львів", image_url: null,
      target_categories: [{ id: 1, name: "УБД" }], offer_categories: [{ id: 2, name: "Кафе" }],
    });
    const src = w.get("img.card__photo").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);
    expect(w.text()).toContain("на все меню");
    expect(w.text()).toContain("Музей");
    expect(w.text()).toContain("УБД");
  });

  it("provider links to the offer detail route; photo uses image_url", () => {
    const w = mountCard({ id: 9, type: "event", title: "Подія", provider: "X", description: "d", image_url: "https://x/y.png", target_categories: [] });
    const link = w.getComponent({ name: "RouterLink" });
    expect(link.props("to")).toEqual({ name: "offer", params: { id: 9 } });
    expect(w.get("img.card__photo").attributes("src")).toBe("https://x/y.png");
  });

  it("shows the description when present", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "Крафтова бургерна", image_url: null, target_categories: [] });
    expect(w.text()).toContain("Крафтова бургерна");
    expect(w.find(".card__desc-empty").exists()).toBe(false);
  });

  it("shows the [опис] placeholder when description is empty", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "", image_url: null, target_categories: [] });
    expect(w.get(".card__desc-empty").text()).toBe("[опис]");
  });

  it("hides the «Для кого» panel when there are no target categories", () => {
    const w = mountCard({ id: 4, type: "discount", title: "T", provider: "P", description: "d", image_url: null, target_categories: [] });
    expect(w.find(".card__whom").exists()).toBe(false);
  });

  it("renders Сайт + Новина links when present", () => {
    const w = mountCard({
      id: 1, type: "discount", title: "T", provider: "Кафе", description: "d",
      site_url: "https://cafe.example", article_url: "https://cafe.example/news",
      image_url: null, target_categories: [],
    });
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://cafe.example");
    expect(hrefs).toContain("https://cafe.example/news");
  });

  it("omits links when absent", () => {
    const w = mountCard({
      id: 2, type: "discount", title: "T", provider: "Кафе", description: "d",
      site_url: null, article_url: null, image_url: null, target_categories: [],
    });
    expect(w.findAll("a.card__link").length).toBe(0);
  });

  it("renders a link pair per offer_link source", () => {
    const w = mountCard({
      id: 5, type: "discount", title: "T", provider: "X", description: "d", image_url: null,
      target_categories: [],
      links: [
        { provider: "Agg1", site_url: "https://agg1", article_url: "https://agg1/p" },
        { provider: "Agg2", site_url: "https://agg2", article_url: "https://agg2/p" },
      ],
    });
    const hrefs = w.findAll("a.card__link").map((a) => a.attributes("href"));
    expect(hrefs).toContain("https://agg1");
    expect(hrefs).toContain("https://agg2");
    expect(hrefs).toContain("https://agg1/p");
    expect(hrefs).toContain("https://agg2/p");
  });
});
