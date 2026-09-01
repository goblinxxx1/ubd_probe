<script setup>
import { reactive, ref, computed, watch } from "vue";
import { OFFER_TYPES } from "@/constants/enums";

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
  types: { type: Array, default: () => [] },
  locations: { type: Array, default: () => [] },
});
const emit = defineEmits(["apply"]);

// Every facet is a multi-select checkbox group; values are stored as strings to match
// the URL query. Search is a plain text field applied on Enter (or when cleared).
const sel = reactive({ type: [], target_category: [], offer_category: [], location: [], q: "" });
const locSearch = ref("");

function toArr(v) {
  if (Array.isArray(v)) return v.map(String);
  return v ? [String(v)] : [];
}

function seed() {
  sel.type = toArr(props.modelValue.type);
  sel.target_category = toArr(props.modelValue.target_category);
  sel.offer_category = toArr(props.modelValue.offer_category);
  sel.location = toArr(props.modelValue.location);
  sel.q = props.modelValue.q || "";
}
// Re-seed whenever the applied filters change (e.g. reset, back/forward). Idempotent when
// modelValue already equals the local selection, so live-apply never loops.
watch(() => props.modelValue, seed, { immediate: true, deep: true });

const activeCount = computed(() => {
  let n = 0;
  for (const k of ["type", "target_category", "offer_category", "location"]) {
    const v = props.modelValue[k];
    if (Array.isArray(v) ? v.length : v) n++;
  }
  if (props.modelValue.q) n++;
  return n;
});

const filteredLocations = computed(() => {
  const term = locSearch.value.trim().toLowerCase();
  return term ? props.locations.filter((c) => c.name.toLowerCase().includes(term)) : props.locations;
});

// Мапа значення типу офера на людський лейбл, тип-опції керуються контекстними
// лічильниками з пропсів (не статичним константним списком).
const TYPE_LABELS = Object.fromEntries(OFFER_TYPES.map((t) => [t.value, t.label]));
const typeOptions = computed(() =>
  props.types.map((t) => ({ value: t.value, count: t.count, label: TYPE_LABELS[t.value] || t.value })),
);

function clean() {
  const out = {};
  if (sel.type.length) out.type = [...sel.type];
  if (sel.target_category.length) out.target_category = [...sel.target_category];
  if (sel.offer_category.length) out.offer_category = [...sel.offer_category];
  if (sel.location.length) out.location = [...sel.location];
  if (sel.q.trim()) out.q = sel.q.trim();
  return out;
}

// Live apply: fired on every checkbox toggle and on search Enter/clear.
function apply() {
  emit("apply", clean());
}

function reset() {
  locSearch.value = "";
  emit("apply", {});
}

defineExpose({ sel, apply, reset, activeCount, filteredLocations, locSearch });
</script>

<template>
  <div class="filters">
    <div class="filters__row filters__row--head">
      <h2 class="filters__title">Фільтри</h2>
      <button v-if="activeCount" class="filters__reset" type="button" @click="reset">
        Скинути<span class="filters__count">{{ activeCount }}</span>
      </button>
    </div>

    <div class="filters__group">
      <label class="filters__label" for="filters-q">Пошук</label>
      <input id="filters-q" v-model="sel.q" type="text" class="filters__search"
             placeholder="Ключове слово" @keyup.enter="apply" @search="apply" />
    </div>

    <fieldset class="filters__group">
      <legend class="filters__label">Для кого</legend>
      <label v-for="c in targetCategories" :key="c.id" class="filters__opt">
        <input type="checkbox" :value="String(c.id)" v-model="sel.target_category" @change="apply" />
        <span class="filters__opt-name">{{ c.name }}</span>
        <span class="filters__cnt">{{ c.count }}</span>
      </label>
    </fieldset>

    <fieldset class="filters__group">
      <legend class="filters__label">Тематика</legend>
      <label v-for="c in offerCategories" :key="c.id" class="filters__opt">
        <input type="checkbox" :value="String(c.id)" v-model="sel.offer_category" @change="apply" />
        <span class="filters__opt-name">{{ c.name }}</span>
        <span class="filters__cnt">{{ c.count }}</span>
      </label>
    </fieldset>

    <fieldset class="filters__group">
      <legend class="filters__label">Тип</legend>
      <label v-for="t in typeOptions" :key="t.value" class="filters__opt">
        <input type="checkbox" :value="t.value" v-model="sel.type" @change="apply" />
        <span class="filters__opt-name">{{ t.label }}</span>
        <span class="filters__cnt">{{ t.count }}</span>
      </label>
    </fieldset>

    <fieldset class="filters__group">
      <legend class="filters__label">Локація</legend>
      <input v-if="locations.length > 8" v-model="locSearch" type="text"
             class="filters__search filters__search--sm" placeholder="Пошук міста" />
      <div class="filters__scroll">
        <label v-for="c in filteredLocations" :key="c.name" class="filters__opt">
          <input type="checkbox" :value="c.name" v-model="sel.location" @change="apply" />
          <span class="filters__opt-name">{{ c.name }}</span>
          <span class="filters__cnt">{{ c.count }}</span>
        </label>
      </div>
    </fieldset>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.filters { display: flex; flex-direction: column; gap: 18px; }
.filters__row--head { display: flex; align-items: center; justify-content: space-between; }
.filters__title { font-size: 18px; font-weight: 800; margin: 0; }
.filters__reset {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; cursor: pointer;
  border: 1px solid @divider; border-radius: 999px; background: @header-bg; color: @text; font-size: 13px;
}
.filters__count { background: @brand; color: @badge-discount-text; border-radius: 999px; padding: 0 7px; font-size: 12px; font-weight: 700; }
.filters__group { border: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.filters__label { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: @meta-muted; padding: 0; }
.filters__search {
  width: 100%; padding: 8px 10px; border: 1px solid @divider; border-radius: @radius-sm;
  font-size: 14px; color: @text; background: @header-bg;
}
.filters__search--sm { padding: 6px 9px; font-size: 13px; }
// checkbox sits LEFT of its label text
.filters__opt {
  display: flex; align-items: center; gap: 9px; font-size: 14px; color: @text; cursor: pointer;
}
.filters__opt input { flex: none; width: 17px; height: 17px; cursor: pointer; }
.filters__opt-name { flex: 1 1 auto; min-width: 0; }
.filters__cnt { flex: none; color: @meta-muted; font-size: 12px; font-variant-numeric: tabular-nums; }
.filters__scroll { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
</style>
