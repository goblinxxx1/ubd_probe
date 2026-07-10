import { defineStore } from "pinia";
import { listTarget, listOffer } from "@/api/categories";

export const useDictionariesStore = defineStore("dictionaries", {
  state: () => ({ targetCategories: [], offerCategories: [], loaded: false }),
  actions: {
    async load() {
      if (this.loaded) return;
      await this.reload();
    },
    async reload() {
      const [target, offer] = await Promise.all([listTarget(), listOffer()]);
      this.targetCategories = target;
      this.offerCategories = offer;
      this.loaded = true;
    },
  },
});
