import { ref, computed, watch, isRef } from "vue";

// Client-side pagination for views that load the whole list at once (Sources,
// Suggested sources, Media-blocklist, Query-terms). Slices a source ref into pages
// and resets to page 1 whenever the source is replaced (reload / filter change).
// `size` may be a plain number (fixed page size) or a ref (adjustable via a
// page-size selector); `setSize` changes it and snaps back to page 1.
export function useClientPagination(source, size = 20) {
  const page = ref(1);
  const sizeRef = isRef(size) ? size : ref(size);
  const total = computed(() => source.value.length);
  const pageItems = computed(() => {
    const start = (page.value - 1) * sizeRef.value;
    return source.value.slice(start, start + sizeRef.value);
  });
  function setPage(p) {
    page.value = p;
  }
  function setSize(s) {
    sizeRef.value = s;
    page.value = 1;
  }
  watch(source, () => {
    page.value = 1;
  });
  return { page, size: sizeRef, total, pageItems, setPage, setSize };
}
