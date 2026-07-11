import { describe, it, expect } from "vitest";
import router from "@/router";

describe("router", () => {
  it("resolves / to the offers route", () => {
    expect(router.resolve("/").name).toBe("offers");
  });
  it("resolves an offer detail path", () => {
    const r = router.resolve("/offers/5");
    expect(r.name).toBe("offer");
    expect(r.params.id).toBe("5");
  });
  it("resolves unknown paths to not-found", () => {
    expect(router.resolve("/nope/here").name).toBe("not-found");
  });
});
