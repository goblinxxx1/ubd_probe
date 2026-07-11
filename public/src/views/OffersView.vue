<script setup>
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useOffers } from "@/composables/useOffers";
import { useDictionaries } from "@/composables/useDictionaries";
import OfferFilters from "@/components/OfferFilters.vue";
import OfferGrid from "@/components/OfferGrid.vue";
import Pagination from "@/components/Pagination.vue";

const route = useRoute();
const router = useRouter();
const { items, total, loading, error, size, page } = useOffers();
const { targetCategories, offerCategories, load: loadDicts } = useDictionaries();

onMounted(loadDicts);

const FILTER_KEYS = ["type", "target_category", "offer_category", "location", "q"];
const currentFilters = computed(() => {
  const f = {};
  for (const k of FILTER_KEYS) if (route.query[k]) f[k] = route.query[k];
  return f;
});

function onApply(filters) {
  router.push({ name: "offers", query: { ...filters } });
}

function onPage(p) {
  router.push({ name: "offers", query: { ...route.query, page: p } });
}

defineExpose({ onApply, onPage });
</script>

<template>
  <div class="container offers">
    <div class="offers__head">
      <h1>Знижки та події для УБД</h1>
      <OfferFilters
        :model-value="currentFilters"
        :target-categories="targetCategories"
        :offer-categories="offerCategories"
        @apply="onApply"
      />
    </div>
    <OfferGrid :offers="items" :loading="loading" :error="error" />
    <Pagination :total="total" :size="size" :page="page" @change="onPage" />
  </div>
</template>

<style scoped lang="less">
.offers__head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.offers__head h1 { font-size: 24px; margin: 0; }
</style>
