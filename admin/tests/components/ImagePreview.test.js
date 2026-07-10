import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ImagePreview from "@/components/ImagePreview.vue";

describe("ImagePreview", () => {
  it("uses the placeholder when imageUrl is empty", () => {
    const wrapper = mount(ImagePreview, { props: { imageUrl: "", type: "event", discountType: null } });
    const src = wrapper.get("img").attributes("src");
    expect(src.startsWith("data:image/svg+xml,")).toBe(true);
    expect(decodeURIComponent(src)).toContain("безкоштовно для УБД");
  });
  it("uses the given url when present", () => {
    const wrapper = mount(ImagePreview, { props: { imageUrl: "https://x/y.png", type: "discount", discountType: "percent" } });
    expect(wrapper.get("img").attributes("src")).toBe("https://x/y.png");
  });
});
