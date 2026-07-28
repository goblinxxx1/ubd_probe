import { ref } from "vue";
import { listTarget, listOffer } from "@/api/categories";
import { locations as fetchLocations } from "@/api/offers";

const targetCategories = ref([]);
const offerCategories = ref([]);
const locations = ref([]);
let loaded = false;
let inflight = null;

export function useDictionaries() {
  async function load() {
    if (loaded) return;
    if (inflight) return inflight;
    inflight = Promise.all([listTarget(), listOffer(), fetchLocations()])
      .then(([t, o, l]) => {
        targetCategories.value = t;
        offerCategories.value = o;
        locations.value = l;
        loaded = true;
      })
      .catch(() => {
        // dictionaries are non-critical (filter options only) — leave lists empty, allow retry
      })
      .finally(() => {
        inflight = null;
      });
    return inflight;
  }
  return { targetCategories, offerCategories, locations, load };
}
