import { describe, it, expect } from "vitest";
import {
  enumLabel,
  formatDate,
  statusTagType,
  isHttpUrl,
  noteSegments,
  discountLabel,
  supersedeSummary,
  discountSummary,
  isJudgeRejected,
} from "@/utils/format";
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

describe("isHttpUrl", () => {
  it("accepts http(s) URLs", () => {
    expect(isHttpUrl("https://x.example")).toBe(true);
    expect(isHttpUrl("http://x.example")).toBe(true);
  });
  it("rejects non-http(s) values", () => {
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("example.com")).toBe(false);
    expect(isHttpUrl("@handle")).toBe(false);
    expect(isHttpUrl(null)).toBe(false);
  });
});

describe("noteSegments", () => {
  it("splits a URL embedded in text into text + url segments", () => {
    expect(noteSegments("active-search offer from https://cafe.example")).toEqual([
      { text: "active-search offer from " },
      { url: "https://cafe.example" },
    ]);
  });
  it("returns a single text segment when there is no URL", () => {
    expect(noteSegments("brand-feed:OKKO")).toEqual([{ text: "brand-feed:OKKO" }]);
  });
  it("handles a URL in the middle of text", () => {
    expect(noteSegments("see https://x.example now")).toEqual([
      { text: "see " },
      { url: "https://x.example" },
      { text: " now" },
    ]);
  });
  it("returns [] for empty/non-string", () => {
    expect(noteSegments("")).toEqual([]);
    expect(noteSegments(null)).toEqual([]);
  });
});

describe("discountLabel", () => {
  it("formats percent without trailing zeros", () => {
    expect(discountLabel("percent", "20.00")).toBe("−20%");
  });
  it("formats fixed", () => {
    expect(discountLabel("fixed", "100.00")).toBe("−100 грн");
  });
  it("formats free", () => {
    expect(discountLabel("free", null)).toBe("безкоштовно");
  });
  it("formats special_price as a plain price (no minus)", () => {
    expect(discountLabel("special_price", "499.00")).toBe("499 грн");
  });
});

describe("supersedeSummary", () => {
  it("summarizes a supersede diff", () => {
    const offer = {
      discount_type: "percent", discount_value: "20.00",
      supersedes: { id: 12, discount_type: "percent", discount_value: "10.00" },
    };
    expect(supersedeSummary(offer)).toBe("замінює #12 (−10% → −20%)");
  });
  it("returns empty for a plain offer", () => {
    expect(supersedeSummary({ supersedes: null })).toBe("");
  });
});

describe("isJudgeRejected", () => {
  it("true when reviewed_by is null and a rejection_reason is set (judge auto-reject)", () => {
    expect(isJudgeRejected({ reviewed_by: null, rejection_reason: "суддя: junk" })).toBe(true);
  });
  it("false when reviewed_by is set (admin reject)", () => {
    expect(isJudgeRejected({ reviewed_by: 3, rejection_reason: "суддя: junk" })).toBe(false);
  });
  it("false when there is no rejection_reason", () => {
    expect(isJudgeRejected({ reviewed_by: null, rejection_reason: null })).toBe(false);
  });
});

describe("discountSummary", () => {
  it("labels a single discount", () => {
    expect(discountSummary({ discount_type: "percent", discount_value: 20 })).toBe("−20%");
  });
  it("counts multiple discounts", () => {
    expect(discountSummary({ discounts: [{}, {}, {}] })).toBe("3 знижок");
  });
  it("returns a dash when there is no discount", () => {
    expect(discountSummary({})).toBe("—");
  });
});

