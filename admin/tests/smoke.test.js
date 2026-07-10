import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import App from "@/App.vue";

describe("App", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("mounts with a router-view", async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", component: { template: "<div>ok</div>" } }],
    });
    router.push("/");
    await router.isReady();
    const wrapper = mount(App, { global: { plugins: [router] } });
    expect(wrapper.html()).toContain("ok");
  });
});
