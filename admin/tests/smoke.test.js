import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import App from "@/App.vue";

describe("App", () => {
  it("mounts and shows the shell fallback", () => {
    const wrapper = mount(App, { global: { config: { globalProperties: { $router: null } } } });
    expect(wrapper.text()).toContain("UBD Admin");
  });
});
