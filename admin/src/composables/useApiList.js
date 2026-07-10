import { ref, reactive } from "vue";

export function useApiList(loader, initialFilters = {}) {
  const items = ref([]);
  const total = ref(0);
  const page = ref(1);
  const size = ref(20);
  const loading = ref(false);
  const filters = reactive({ ...initialFilters });

  async function load() {
    loading.value = true;
    try {
      const result = await loader({ ...filters, page: page.value, size: size.value });
      if (Array.isArray(result)) {
        items.value = result;
        total.value = result.length;
      } else {
        items.value = result.items;
        total.value = result.total;
      }
    } finally {
      loading.value = false;
    }
  }

  function setPage(p) {
    page.value = p;
    return load();
  }

  function applyFilters(patch) {
    Object.assign(filters, patch);
    page.value = 1;
    return load();
  }

  return { items, total, page, size, loading, filters, load, setPage, applyFilters };
}
