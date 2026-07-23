import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus from "element-plus";
import AdminLayout from "@/layouts/AdminLayout.vue";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/api/offers", () => ({ list: vi.fn(() => Promise.resolve({ items: [], total: 0 })) }));

function makeRouter() {
  const stub = { template: "<div/>" };
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "offers", component: stub },
      { path: "/categories", name: "categories", component: stub },
      { path: "/users", name: "users", component: stub },
      { path: "/moderation", name: "moderation", component: stub },
      { path: "/sources", name: "sources", component: stub },
      { path: "/suggested-sources", name: "suggested-sources", component: stub },
      { path: "/host-candidates", name: "host-candidates", component: stub },
      { path: "/login", name: "login", component: stub },
    ],
  });
}

describe("AdminLayout", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("hides super_admin links for a moderator", async () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "moderator";
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(AdminLayout, { global: { plugins: [router, ElementPlus] } });
    expect(wrapper.text()).not.toContain("Категорії");
    expect(wrapper.text()).not.toContain("Адміни");
    expect(wrapper.text()).toContain("Оффери");
  });

  it("shows super_admin links for a super_admin", async () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "super_admin";
    const router = makeRouter();
    router.push("/");
    await router.isReady();
    const wrapper = mount(AdminLayout, { global: { plugins: [router, ElementPlus] } });
    expect(wrapper.text()).toContain("Категорії");
    expect(wrapper.text()).toContain("Адміни");
  });
});

describe("AdminLayout drawer", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("starts closed and toggles open", async () => {
    const stubs = { "router-link": true, "router-view": true };
    const w = mount(AdminLayout, { global: { plugins: [ElementPlus, createPinia()], stubs } });
    expect(w.vm.drawerOpen).toBe(false);
    w.vm.drawerOpen = true;
    await w.vm.$nextTick();
    expect(w.find(".sidebar--open").exists()).toBe(true);
  });
});
