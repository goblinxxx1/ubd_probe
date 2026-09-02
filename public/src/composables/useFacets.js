import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { facets as fetchFacets } from "@/api/offers";

const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];

export function useFacets() {
  const route = useRoute();
  const targetCategories = ref([]);
  const offerCategories = ref([]);
  const types = ref([]);
  const locations = ref([]);
  // Монотонний лічильник запитів: за швидких змін фільтра застосовуємо лише
  // найновіший знімок, щоб застаріла відповідь не перекрила свіжу.
  let requestId = 0;

  function paramsFromQuery(query) {
    const params = {};
    for (const key of FILTER_KEYS) if (query[key]) params[key] = query[key];
    return params;
  }

  async function load() {
    const rid = ++requestId;
    try {
      // Контекстні лічильники залежать від активних фільтрів — перезавантажуємо на кожну зміну.
      const data = await fetchFacets(paramsFromQuery(route.query));
      if (rid !== requestId) return;   // новіший запит переміг — відкидаємо застарілу відповідь
      targetCategories.value = data.target_categories;
      offerCategories.value = data.offer_categories;
      types.value = data.types;
      locations.value = data.locations;
    } catch {
      // Фасети — некритична прикраса фільтрів: лишаємо останній знімок (без блимання), повторимо на наступній зміні.
    }
  }

  watch(() => route.query, load, { immediate: true });

  return { targetCategories, offerCategories, types, locations, load };
}
