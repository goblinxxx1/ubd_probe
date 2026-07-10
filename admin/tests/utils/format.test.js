import { describe, it, expect } from "vitest";
import { enumLabel, formatDate, statusTagType } from "@/utils/format";
import { OFFER_STATUSES } from "@/constants/enums";

describe("enumLabel", () => {
  it("returns the label for a known value", () => {
    expect(enumLabel(OFFER_STATUSES, "published")).toBe("Опубліковано");
  });
  it("falls back to the raw value when unknown", () => {
    expect(enumLabel(OFFER_STATUSES, "weird")).toBe("weird");
  });
});

describe("formatDate", () => {
  it("formats an ISO date as dd.mm.yyyy", () => {
    expect(formatDate("2026-07-01")).toBe("01.07.2026");
  });
  it("returns empty string for null/empty", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate("")).toBe("");
  });
});

describe("statusTagType", () => {
  it("maps statuses to Element Plus tag types", () => {
    expect(statusTagType("pending_review")).toBe("warning");
    expect(statusTagType("published")).toBe("success");
    expect(statusTagType("rejected")).toBe("danger");
    expect(statusTagType("expired")).toBe("info");
  });
});
