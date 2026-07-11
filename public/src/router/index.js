import { createRouter, createWebHistory } from "vue-router";
import OffersView from "@/views/OffersView.vue";
import OfferDetailView from "@/views/OfferDetailView.vue";
import NotFoundView from "@/views/NotFoundView.vue";

const routes = [
  { path: "/", name: "offers", component: OffersView },
  { path: "/offers/:id", name: "offer", component: OfferDetailView },
  { path: "/:catchAll(.*)", name: "not-found", component: NotFoundView },
];

const router = createRouter({ history: createWebHistory(), routes });

export default router;
