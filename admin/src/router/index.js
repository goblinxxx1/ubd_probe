import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import AdminLayout from "@/layouts/AdminLayout.vue";
import LoginView from "@/views/LoginView.vue";
import OffersListView from "@/views/OffersListView.vue";
import ModerationQueueView from "@/views/ModerationQueueView.vue";
import OfferFormView from "@/views/OfferFormView.vue";
import SourcesView from "@/views/SourcesView.vue";
import SuggestedSourcesView from "@/views/SuggestedSourcesView.vue";
import HostCandidatesView from "@/views/HostCandidatesView.vue";
import CategoriesView from "@/views/CategoriesView.vue";
import AdminUsersView from "@/views/AdminUsersView.vue";

const routes = [
  { path: "/login", name: "login", meta: { public: true }, component: LoginView },
  {
    path: "/",
    component: AdminLayout,
    children: [
      { path: "", name: "offers", component: OffersListView },
      { path: "moderation", name: "moderation", component: ModerationQueueView },
      { path: "offers/new", name: "offer-new", component: OfferFormView },
      { path: "offers/:id/edit", name: "offer-edit", component: OfferFormView },
      { path: "sources", name: "sources", component: SourcesView },
      { path: "suggested-sources", name: "suggested-sources", component: SuggestedSourcesView },
      { path: "host-candidates", name: "host-candidates", component: HostCandidatesView },
      { path: "categories", name: "categories", meta: { superAdmin: true }, component: CategoriesView },
      { path: "users", name: "users", meta: { superAdmin: true }, component: AdminUsersView },
    ],
  },
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
