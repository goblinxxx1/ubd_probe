import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const Placeholder = { template: "<div />" };

const routes = [
  { path: "/login", name: "login", meta: { public: true }, component: Placeholder },
  { path: "/", name: "offers", component: Placeholder },
  { path: "/moderation", name: "moderation", component: Placeholder },
  { path: "/offers/new", name: "offer-new", component: Placeholder },
  { path: "/offers/:id/edit", name: "offer-edit", component: Placeholder },
  { path: "/sources", name: "sources", component: Placeholder },
  { path: "/suggested-sources", name: "suggested-sources", component: Placeholder },
  { path: "/categories", name: "categories", meta: { superAdmin: true }, component: Placeholder },
  { path: "/users", name: "users", meta: { superAdmin: true }, component: Placeholder },
];

export function navigationGuard(to) {
  const auth = useAuthStore();
  if (to.meta.public) return true;
  if (!auth.isAuthenticated) return { name: "login" };
  if (to.meta.superAdmin && !auth.isSuperAdmin) return { name: "offers" };
  return true;
}

const router = createRouter({ history: createWebHistory(), routes });
router.beforeEach((to) => navigationGuard(to));

export default router;
