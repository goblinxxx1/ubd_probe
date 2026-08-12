<script setup>
import { computed, ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useOffers } from "@/composables/useOffers";
import { useDictionaries } from "@/composables/useDictionaries";
import OfferFilters from "@/components/OfferFilters.vue";
import OfferGrid from "@/components/OfferGrid.vue";
import Pagination from "@/components/Pagination.vue";

const route = useRoute();
const router = useRouter();
const { items, total, loading, error, size, page } = useOffers();
const { targetCategories, offerCategories, locations, load: loadDicts } = useDictionaries();

onMounted(loadDicts);

const filtersOpen = ref(false);   // mobile drawer

const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];
const currentFilters = computed(() => {
  const f = {};
  for (const k of FILTER_KEYS) if (route.query[k]) f[k] = route.query[k];
  return f;
});

const activeCount = computed(() => {
  let n = 0;
  for (const k of FILTER_KEYS) {
    const v = route.query[k];
    if (Array.isArray(v) ? v.length : v) n++;
  }
  return n;
});

function onApply(filters) {
  router.push({ name: "offers", query: { ...filters } });   // resets to page 1
}

function onPage(p) {
  router.push({ name: "offers", query: { ...route.query, page: p } });
}

defineExpose({ onApply, onPage, filtersOpen });
</script>

<template>
  <div class="container offers">
    <div class="offers__head">
      <h1>Знижки та події для УБД</h1>
      <button class="offers__toggle" type="button" @click="filtersOpen = true">
        Фільтри<span v-if="activeCount" class="offers__toggle-count">{{ activeCount }}</span>
      </button>
    </div>

    <div class="offers__body">
      <div v-if="filtersOpen" class="offers__backdrop" @click="filtersOpen = false"></div>
      <aside class="offers__rail" :class="{ 'is-open': filtersOpen }">
        <div class="offers__rail-head">
          <span>Фільтри</span>
          <button class="offers__rail-close" type="button" @click="filtersOpen = false" aria-label="Закрити">×</button>
        </div>
        <OfferFilters
          :model-value="currentFilters"
          :target-categories="targetCategories"
          :offer-categories="offerCategories"
          :locations="locations"
          @apply="onApply"
        />
      </aside>

      <main class="offers__main">
        <OfferGrid :offers="items" :loading="loading" :error="error" />
        <Pagination :total="total" :size="size" :page="page" @change="onPage" />
      </main>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.offers__head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.offers__head h1 { font-size: 24px; margin: 0; font-weight: 700; }

.offers__body { display: grid; grid-template-columns: 260px 1fr; gap: 22px; align-items: start; }
.offers__rail {
  position: sticky; top: 16px; align-self: start;
  background: @card-bg; border: 1px solid @divider; border-radius: @radius; padding: 16px;
}
.offers__rail-head, .offers__rail-close, .offers__toggle, .offers__backdrop { display: none; }   // desktop: sidebar always visible
.offers__main { min-width: 0; }   // let the grid shrink instead of overflowing

@media (max-width: @bp-mobile) {
  .offers__body { grid-template-columns: 1fr; }
  .offers__toggle {
    display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; cursor: pointer;
    border: 1px solid @divider; border-radius: @radius-sm; background: @header-bg; color: @text;
    font-size: 13px; text-transform: uppercase; letter-spacing: .5px;
  }
  .offers__toggle-count { background: @brand; color: @badge-discount-text; border-radius: 999px; padding: 0 7px; font-size: 12px; font-weight: 700; }
  // off-canvas drawer
  .offers__rail {
    position: fixed; z-index: 1001; top: 0; left: 0; bottom: 0; width: min(320px, 88vw);
    border-radius: 0; overflow-y: auto; transform: translateX(-100%); transition: transform .22s ease;
  }
  .offers__rail.is-open { transform: translateX(0); }
  .offers__rail-head {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
    font-weight: 800; font-size: 18px;
  }
  .offers__rail-close { display: inline-block; background: none; border: none; font-size: 26px; line-height: 1; cursor: pointer; color: @text; }
  .offers__backdrop { display: block; position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,.45); }
}
</style>
