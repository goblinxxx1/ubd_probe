import { describe, it, expect, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import App from "@/App.vue";
import router from "@/router";

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
