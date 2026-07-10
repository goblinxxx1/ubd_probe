import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/auth", () => ({
  login: vi.fn(() => Promise.resolve({ access_token: "tok", token_type: "bearer", role: "super_admin" })),
}));

import { useAuthStore } from "@/stores/auth";
import { login as loginApi } from "@/api/auth";

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("login stores token and role", async () => {
    const store = useAuthStore();
    await store.login("a@b.c", "pw");
    expect(loginApi).toHaveBeenCalledWith("a@b.c", "pw");
    expect(store.token).toBe("tok");
    expect(store.role).toBe("super_admin");
    expect(store.isAuthenticated).toBe(true);
    expect(store.isSuperAdmin).toBe(true);
    expect(localStorage.getItem("ubd_admin_token")).toBe("tok");
    expect(localStorage.getItem("ubd_admin_role")).toBe("super_admin");
  });

  it("logout clears token and role", async () => {
    const store = useAuthStore();
    await store.login("a@b.c", "pw");
    store.logout();
    expect(store.token).toBe(null);
    expect(store.isAuthenticated).toBe(false);
    expect(localStorage.getItem("ubd_admin_token")).toBe(null);
  });
});
