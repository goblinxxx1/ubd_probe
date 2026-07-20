import { describe, it, expect } from "vitest";
import { mount, RouterLinkStub } from "@vue/test-utils";
import SiteHeader from "@/components/SiteHeader.vue";

describe("SiteHeader", () => {
  it("links Оффери to the offers route via the nav link", () => {
    const w = mount(SiteHeader, { global: { stubs: { RouterLink: RouterLinkStub } } });
    const navLink = w.findComponent(".nav__link");
    expect(navLink.exists()).toBe(true);
    expect(navLink.props("to")).toEqual({ name: "offers" });
    expect(navLink.text()).toBe("Оффери");
    expect(w.text()).not.toContain("Про нас");
  });
});
