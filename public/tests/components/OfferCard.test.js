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

  it("hides the footer entirely when there is no meta and no links", () => {
    const w = mountCard({
      id: 6, type: "discount", title: "T", provider: "P", description: "d",
      location: null, image_url: null, target_categories: [], offer_categories: [],
      site_url: null, article_url: null,
    });
    expect(w.find(".card__foot").exists()).toBe(false);
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

  it("shows the discount-title even when it equals the description", () => {
    const w = mountCard({
      id: 10, type: "discount", title: "Знижка 20% для ветеранів",
      provider: "P", description: "Знижка 20% для ветеранів",
      image_url: null, target_categories: [],
    });
    expect(w.get(".card__dtext").text()).toBe("Знижка 20% для ветеранів");
  });

  it("shows the discount-title even when the description starts with it", () => {
    const w = mountCard({
      id: 11, type: "discount", title: "Знижка 20%",
      provider: "P", description: "Знижка 20% для ветеранів у нашому кафе",
      image_url: null, target_categories: [],
    });
    expect(w.get(".card__dtext").text()).toBe("Знижка 20%");
  });

  it("shows the discount-title when it is distinct from the description", () => {
    const w = mountCard({
      id: 12, type: "discount", title: "на все меню",
      provider: "P", description: "Крафтова бургерна у центрі міста",
      image_url: null, target_categories: [],
    });
    expect(w.get(".card__dtext").text()).toBe("на все меню");
  });

  it("sets the photo alt to the provider name", () => {
    const w = mountCard({ id: 7, type: "discount", title: "T", provider: "Кав'ярня Львів", description: "d", image_url: null, target_categories: [] });
    expect(w.get("img.card__photo").attributes("alt")).toBe("Кав'ярня Львів");
  });

  it("renders all offer_categories as chips", () => {
    const w = mountCard({
      id: 11, type: "discount", title: "Бізнес-опис", provider: "P", description: "d",
      image_url: null, target_categories: [],
      offer_categories: [{ id: 2, name: "Кафе" }, { id: 3, name: "Спорт" }],
    });
    expect(w.text()).toContain("Кафе");
    expect(w.text()).toContain("Спорт");
  });

  it("always shows card__dtext when title is present, even if description repeats it", () => {
    const w = mountCard({
      id: 12, type: "discount", title: "Знижка для ЗСУ", provider: "P",
      description: "Знижка для ЗСУ та ще купа тексту опису", image_url: null,
      target_categories: [], offer_categories: [],
    });
    expect(w.find(".card__dtext").exists()).toBe(true);
    expect(w.get(".card__dtext").text()).toBe("Знижка для ЗСУ");
  });

  it("shows all offer cities joined in the footer meta", () => {
    const w = mountCard({
      id: 20, type: "discount", title: "T", provider: "P", description: "d", image_url: null,
      target_categories: [], offer_categories: [], locations: ["Київ", "Львів"],
    });
    expect(w.get(".card__meta").text()).toBe("Київ · Львів");
  });

  it("renders each discount with its label", () => {
    const w = mountCard({
      id: 21, provider: "Кафе", type: "discount",
      discount_type: "percent", discount_value: 15,
      discounts: [
        { label: "МВС", discount_type: "percent", discount_value: 10 },
        { label: "ЗСУ", discount_type: "percent", discount_value: 15 },
      ],
      target_categories: [], offer_categories: [], locations: [],
    });
    const text = w.text();
    expect(text).toContain("МВС");
    expect(text).toContain("ЗСУ");
    expect(text).toContain("−10%");
    expect(text).toContain("−15%");
  });

  it("uses the brand logo as the single card image when present (prefers it over the hero photo)", () => {
    const w = mountCard({
      id: 30, type: "discount", title: "T", provider: "WoodMall", description: "d",
      image_url: "https://x/hero.jpg", logo_url: "https://woodmallcinema.com/img/logo.svg",
      target_categories: [], offer_categories: [], locations: [],
    });
    // one image only, and it is the logo — no separate badge
    expect(w.get("img.card__photo").attributes("src")).toBe("https://woodmallcinema.com/img/logo.svg");
    expect(w.findAll("img").length).toBe(1);
    expect(w.html()).not.toContain("<svg");   // rendered via <img src>, never inlined
  });

  it("falls back to the placeholder when the image fails to load (broken/blocked remote URL)", async () => {
    const w = mountCard({
      id: 40, type: "discount", discount_type: "free", title: "T", provider: "P", description: "d",
      logo_url: "https://estro.ua/blocked-403.svg",
      target_categories: [], offer_categories: [], locations: [],
    });
    const img = w.get("img.card__photo");
    expect(img.attributes("src")).toBe("https://estro.ua/blocked-403.svg"); // starts with the logo
    await img.trigger("error");                                             // remote load fails (403/404/bad URL)
    const src = w.get("img.card__photo").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);              // degraded to placeholder, not a broken icon
  });

  it("on a dead logo, tries the hero photo before the placeholder", async () => {
    const w = mountCard({
      id: 41, type: "discount", title: "T", provider: "P", description: "d",
      logo_url: "https://dead.example/logo.svg", image_url: "https://live.example/hero.jpg",
      target_categories: [], offer_categories: [], locations: [],
    });
    const img = w.get("img.card__photo");
    expect(img.attributes("src")).toBe("https://dead.example/logo.svg");   // logo first
    await img.trigger("error");
    expect(w.get("img.card__photo").attributes("src")).toBe("https://live.example/hero.jpg"); // then hero
    await w.get("img.card__photo").trigger("error");
    expect(w.get("img.card__photo").attributes("src").startsWith("data:image/svg+xml,")).toBe(true); // then placeholder
  });

  it("falls back to the hero photo when there is no logo", () => {
    const w = mountCard({
      id: 31, type: "discount", title: "T", provider: "P", description: "d",
      image_url: "https://x/hero.jpg", logo_url: null,
      target_categories: [], offer_categories: [], locations: [],
    });
    expect(w.get("img.card__photo").attributes("src")).toBe("https://x/hero.jpg");
  });

  it("hides the discount list when there is only one discount", () => {
    const w = mountCard({
      id: 22, provider: "Кафе", type: "discount",
      discount_type: "percent", discount_value: 15,
      discounts: [{ label: "МВС", discount_type: "percent", discount_value: 15 }],
      target_categories: [], offer_categories: [], locations: [],
    });
    expect(w.find(".card__discounts").exists()).toBe(false);
  });
});
