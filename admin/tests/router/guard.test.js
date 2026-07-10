import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { navigationGuard } from "@/router";
import { useAuthStore } from "@/stores/auth";

describe("navigationGuard", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("redirects unauthenticated users to login", () => {
    expect(navigationGuard({ meta: {}, name: "offers" })).toEqual({ name: "login" });
  });

  it("allows the public login route", () => {
    expect(navigationGuard({ meta: { public: true }, name: "login" })).toBe(true);
  });

  it("blocks moderator from super_admin routes", () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "moderator";
    expect(navigationGuard({ meta: { superAdmin: true }, name: "users" })).toEqual({ name: "offers" });
  });

  it("allows super_admin everywhere", () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.role = "super_admin";
    expect(navigationGuard({ meta: { superAdmin: true }, name: "users" })).toBe(true);
  });
});
