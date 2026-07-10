import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ElementPlus from "element-plus";
import AdminUsersView from "@/views/AdminUsersView.vue";

vi.mock("@/api/users", () => ({
  list: vi.fn(() => Promise.resolve([{ id: 1, email: "a@b.c", role: "super_admin", created_at: "2026-07-01" }])),
  create: vi.fn(() => Promise.resolve({})),
  remove: vi.fn(() => Promise.resolve({})),
}));
vi.mock("@/utils/confirm", () => ({ confirmDelete: vi.fn(() => Promise.resolve()) }));
vi.mock("element-plus", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn() } };
});
import * as users from "@/api/users";

describe("AdminUsersView", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads users on mount", async () => {
    mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    expect(users.list).toHaveBeenCalled();
  });

  it("creates a user", async () => {
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    Object.assign(wrapper.vm.form, { email: "new@b.c", password: "pw123456", role: "moderator" });
    await wrapper.vm.create();
    await flushPromises();
    expect(users.create).toHaveBeenCalledWith({ email: "new@b.c", password: "pw123456", role: "moderator" });
    expect(users.list).toHaveBeenCalledTimes(2);
  });

  it("deletes a user", async () => {
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } });
    await flushPromises();
    await wrapper.vm.onDelete(1);
    await flushPromises();
    expect(users.remove).toHaveBeenCalledWith(1);
  });
});
