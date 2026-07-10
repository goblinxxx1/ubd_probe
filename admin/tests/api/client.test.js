import { describe, it, expect, vi, beforeEach } from "vitest";
import { extractError } from "@/utils/errors";

describe("extractError", () => {
  it("prefers backend detail", () => {
    expect(extractError({ response: { data: { detail: "Немає доступу", code: "forbidden" } } })).toBe("Немає доступу");
  });
  it("falls back to message", () => {
    expect(extractError({ message: "Network Error" })).toBe("Network Error");
  });
  it("has a final fallback", () => {
    expect(extractError({})).toBe("Сталася помилка");
  });
});

describe("client interceptors", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("attaches the bearer token from localStorage", async () => {
    localStorage.setItem("ubd_admin_token", "tok123");
    const { default: client } = await import("@/api/client");
    const handlers = client.interceptors.request.handlers;
    const config = await handlers[0].fulfilled({ headers: {} });
    expect(config.headers.Authorization).toBe("Bearer tok123");
  });

  it("calls the unauthorized handler on 401", async () => {
    const { default: client, setUnauthorizedHandler } = await import("@/api/client");
    const spy = vi.fn();
    setUnauthorizedHandler(spy);
    const rejected = client.interceptors.response.handlers[0].rejected;
    await expect(rejected({ response: { status: 401 } })).rejects.toBeTruthy();
    expect(spy).toHaveBeenCalledOnce();
  });
});
