import { defineStore } from "pinia";
import { login as loginApi } from "@/api/auth";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("ubd_admin_token") || null,
    role: localStorage.getItem("ubd_admin_role") || null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    isSuperAdmin: (state) => state.role === "super_admin",
  },
  actions: {
    async login(email, password) {
      const data = await loginApi(email, password);
      this.token = data.access_token;
      this.role = data.role;
      localStorage.setItem("ubd_admin_token", this.token);
      localStorage.setItem("ubd_admin_role", this.role);
    },
    logout() {
      this.token = null;
      this.role = null;
      localStorage.removeItem("ubd_admin_token");
      localStorage.removeItem("ubd_admin_role");
    },
  },
});
