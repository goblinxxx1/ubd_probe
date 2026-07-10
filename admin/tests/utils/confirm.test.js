import { describe, it, expect, vi } from "vitest";

vi.mock("element-plus", () => ({
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}));
import { ElMessageBox } from "element-plus";
import { confirmDelete } from "@/utils/confirm";

describe("confirmDelete", () => {
  it("calls ElMessageBox.confirm with the message", async () => {
    await confirmDelete("Прибрати?");
    expect(ElMessageBox.confirm).toHaveBeenCalled();
    expect(ElMessageBox.confirm.mock.calls[0][0]).toBe("Прибрати?");
  });
});
