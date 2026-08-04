import { ref, computed, watch } from "vue";

// Client-side pagination for views that load the whole list at once (Sources,
// Suggested sources, Media-blocklist). Slices a source ref into pages and resets
// to page 1 whenever the source is replaced (reload / filter change).
export function useClientPagination(source, size = 20) {
  const page = ref(1);
  const total = computed(() => source.value.length);
  const pageItems = computed(() => {
    const start = (page.value - 1) * size;
    return source.value.slice(start, start + size);
  });
  function setPage(p) {
    page.value = p;
  }
  watch(source, () => {
    page.value = 1;
  });
  return { page, size, total, pageItems, setPage };
}
