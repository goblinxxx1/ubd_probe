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
});
