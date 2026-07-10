import { defineStore } from "pinia";
import { listTarget, listOffer } from "@/api/categories";

export const useDictionariesStore = defineStore("dictionaries", {
  state: () => ({ targetCategories: [], offerCategories: [], loaded: false, loadPromise: null }),
  actions: {
    async load() {
      if (this.loaded) return;
      if (this.loadPromise) return this.loadPromise;
      this.loadPromise = this.reload().finally(() => {
        this.loadPromise = null;
      });
      return this.loadPromise;
    },
    async reload() {
      const [target, offer] = await Promise.all([listTarget(), listOffer()]);
      this.targetCategories = target;
      this.offerCategories = offer;
      this.loaded = true;
    },
  },
});
