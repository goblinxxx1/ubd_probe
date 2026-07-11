import { ref } from "vue";
import { listTarget, listOffer } from "@/api/categories";

const targetCategories = ref([]);
const offerCategories = ref([]);
let loaded = false;
let inflight = null;

export function useDictionaries() {
  async function load() {
    if (loaded) return;
    if (inflight) return inflight;
    inflight = Promise.all([listTarget(), listOffer()])
      .then(([t, o]) => {
        targetCategories.value = t;
        offerCategories.value = o;
        loaded = true;
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }
  return { targetCategories, offerCategories, load };
}
