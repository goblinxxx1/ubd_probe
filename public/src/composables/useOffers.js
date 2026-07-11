import { ref, computed, watch } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { extractError } from "@/utils/errors";

const SIZE = 12;
const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];

export function useOffers() {
  const route = useRoute();
  const items = ref([]);
  const total = ref(0);
  const loading = ref(false);
  const error = ref(null);
  const page = computed(() => Number(route.query.page) || 1);

  function paramsFromQuery(query) {
    const params = { page: page.value, size: SIZE };
    for (const key of FILTER_KEYS) {
      if (query[key]) params[key] = query[key];
    }
    return params;
  }

  async function load() {
    loading.value = true;
    error.value = null;
    try {
      const data = await offersApi.list(paramsFromQuery(route.query));
      items.value = data.items;
      total.value = data.total;
    } catch (e) {
      error.value = extractError(e);
      items.value = [];
      total.value = 0;
    } finally {
      loading.value = false;
    }
  }

  watch(() => route.query, load, { immediate: true });

  return { items, total, loading, error, size: SIZE, page, load };
}
