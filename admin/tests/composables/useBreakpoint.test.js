import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { useBreakpoint } from "@/composables/useBreakpoint";

function harness() {
  return mount({ template: "<div/>", setup() { return useBreakpoint(); } });
}

describe("useBreakpoint", () => {
  it("is desktop when matchMedia reports no match", () => {
    window.matchMedia = vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    const w = harness();
    expect(w.vm.isMobile).toBe(false);
    expect(w.vm.isTablet).toBe(false);
  });

  it("is mobile+tablet when both queries match", () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    const w = harness();
    expect(w.vm.isMobile).toBe(true);
    expect(w.vm.isTablet).toBe(true);
  });

  it("updates reactively when the media query fires a change event", async () => {
    let mobileMatches = false;
    const listeners = {};
    window.matchMedia = vi.fn((query) => ({
      get matches() { return query.includes("640") ? mobileMatches : false; },
      addEventListener(_evt, cb) { listeners[query] = cb; },
      removeEventListener() {},
    }));
    const w = harness();
    expect(w.vm.isMobile).toBe(false);

    mobileMatches = true;
    listeners["(max-width: 640px)"](); // simulate the viewport crossing the breakpoint
    await w.vm.$nextTick();
    expect(w.vm.isMobile).toBe(true);
  });
});
