import { describe, it, expect } from "vitest";
import { mount, RouterLinkStub } from "@vue/test-utils";
import SiteHeader from "@/components/SiteHeader.vue";

describe("SiteHeader", () => {
  it("links Оффери to the offers route", () => {
    const w = mount(SiteHeader, { global: { stubs: { RouterLink: RouterLinkStub } } });
    const links = w.findAllComponents(RouterLinkStub);
    const offers = links.find((l) => l.props("to")?.name === "offers");
    expect(offers).toBeTruthy();
    expect(w.text()).not.toContain("Про нас");
  });
});
