import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import ElementPlus, { ElMessage } from "element-plus";
import LoginView from "@/views/LoginView.vue";

vi.mock("@/api/auth", () => ({ login: vi.fn() }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { error: vi.fn(), success: vi.fn() } };
});
import { login as loginApi } from "@/api/auth";

function makeRouter() {
  const stub = { template: "<div/>" };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: stub },
      { path: "/", name: "offers", component: stub },
    ],
  });
  return router;
}

describe("LoginView", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("routes to offers on successful login", async () => {
    loginApi.mockResolvedValue({ access_token: "t", token_type: "bearer", role: "moderator" });
    const router = makeRouter();
    router.push("/login");
    await router.isReady();
    const push = vi.spyOn(router, "push");
    const wrapper = mount(LoginView, { global: { plugins: [router, ElementPlus] } });
    wrapper.vm.form.email = "a@b.c";
    wrapper.vm.form.password = "pw";
    await wrapper.vm.submit();
    await flushPromises();
    expect(loginApi).toHaveBeenCalledWith("a@b.c", "pw");
    expect(push).toHaveBeenCalledWith({ name: "offers" });
  });

  it("shows an error message on failed login", async () => {
    loginApi.mockRejectedValue({ response: { data: { detail: "Invalid credentials", code: "unauthorized" } } });
    const router = makeRouter();
    router.push("/login");
    await router.isReady();
    const wrapper = mount(LoginView, { global: { plugins: [router, ElementPlus] } });
    wrapper.vm.form.email = "a@b.c";
    wrapper.vm.form.password = "bad";
    await wrapper.vm.submit();
    await flushPromises();
    expect(ElMessage.error).toHaveBeenCalledWith("Invalid credentials");
  });
});
