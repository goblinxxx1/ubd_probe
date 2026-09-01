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
  const loading = ref(false);        // початкове/скидне завантаження
  const loadingMore = ref(false);    // довантаження (кнопка «Завантажити ще»)
  const error = ref(null);
  const page = computed(() => Number(route.query.page) || 1);   // базова сторінка для нумерованого пейджера
  const loadedPage = ref(page.value);
  const hasMore = computed(() => items.value.length < total.value);

  function paramsForPage(p) {
    const params = { page: p, size: SIZE };
    for (const key of FILTER_KEYS) if (route.query[key]) params[key] = route.query[key];
    return params;
  }

  async function load() {
    loading.value = true;
    error.value = null;
    loadedPage.value = page.value;
    try {
      const data = await offersApi.list(paramsForPage(page.value));
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

  async function loadMore() {
    if (loadingMore.value || !hasMore.value) return;
    loadingMore.value = true;
    error.value = null;
    try {
      const next = loadedPage.value + 1;
      const data = await offersApi.list(paramsForPage(next));
      items.value = [...items.value, ...data.items];
      total.value = data.total;
      loadedPage.value = next;
    } catch (e) {
      error.value = extractError(e);
    } finally {
      loadingMore.value = false;
    }
  }

  watch(() => route.query, load, { immediate: true });

  return { items, total, loading, loadingMore, error, size: SIZE, page, hasMore, load, loadMore };
}
