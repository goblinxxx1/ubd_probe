<script setup>
import { reactive, ref, computed, watch } from "vue";
import { OFFER_TYPES } from "@/constants/enums";

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
});
const emit = defineEmits(["apply"]);

const open = ref(false);
const draft = reactive({ type: "", target_category: "", offer_category: "", location: "", q: "" });

function seed() {
  draft.type = props.modelValue.type || "";
  draft.target_category = props.modelValue.target_category || "";
  draft.offer_category = props.modelValue.offer_category || "";
  draft.location = props.modelValue.location || "";
  draft.q = props.modelValue.q || "";
}
watch(open, (isOpen) => { if (isOpen) seed(); });

const activeCount = computed(
  () => ["type", "target_category", "offer_category", "location", "q"].filter((k) => props.modelValue[k]).length
);

function clean() {
  const out = {};
  for (const k of ["type", "target_category", "offer_category", "location", "q"]) {
    if (draft[k]) out[k] = draft[k];
  }
  return out;
}

function apply() {
  emit("apply", clean());
  open.value = false;
}

function reset() {
  emit("apply", {});
  open.value = false;
}

defineExpose({ open, draft, apply, reset, activeCount });
</script>

<template>
  <div class="filters">
    <button class="filters__trigger" @click="open = !open">
      Фільтри<span v-if="activeCount" class="filters__count">{{ activeCount }}</span>
    </button>

    <div v-if="open" class="filters__backdrop" @click="open = false"></div>

    <div v-if="open" class="filters__panel">
      <label>Тип
        <select v-model="draft.type">
          <option value="">Усі</option>
          <option v-for="t in OFFER_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </label>
      <label>Для кого
        <select v-model="draft.target_category">
          <option value="">Усі</option>
          <option v-for="c in targetCategories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </label>
      <label>Тематика
        <select v-model="draft.offer_category">
          <option value="">Усі</option>
          <option v-for="c in offerCategories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </label>
      <label>Локація
        <input v-model="draft.location" type="text" placeholder="Місто або «онлайн»" />
      </label>
      <label>Пошук
        <input v-model="draft.q" type="text" placeholder="Ключове слово" @keyup.enter="apply" />
      </label>
      <div class="filters__actions">
        <button class="btn btn--primary" @click="apply">Застосувати</button>
        <button class="btn" @click="reset">Скинути</button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.filters { position: relative; display: inline-block; }
.filters__trigger {
  padding: 6px 12px; border: 1px solid @divider; border-radius: @radius-sm; background: @header-bg;
  cursor: pointer; font-size: 13px; color: @text; text-transform: uppercase; letter-spacing: .5px;
}
.filters__count { margin-left: 6px; background: @brand; color: @badge-discount-text; border-radius: 999px; padding: 0 7px; font-size: 12px; font-weight: 700; }
.filters__backdrop { position: fixed; inset: 0; z-index: 10; }
.filters__panel {
  position: absolute; z-index: 11; top: calc(100% + 6px); left: 0; width: min(320px, 90vw);
  background: @header-bg; border: 1px solid @divider; border-radius: @radius;
  box-shadow: 0 8px 28px rgba(0,0,0,0.10); padding: 14px; display: flex; flex-direction: column; gap: 10px;
}
.filters__panel label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: @meta-muted; }
.filters__panel select, .filters__panel input { padding: 7px; border: 1px solid @divider; border-radius: @radius-sm; font-size: 15px; color: @text; }
.filters__actions { display: flex; gap: 8px; margin-top: 4px; }
.btn { padding: 8px 12px; border: 1px solid @divider; border-radius: @radius-sm; background: @header-bg; cursor: pointer; color: @text; }
.btn--primary { background: @dark; color: @chip-text; border-color: @dark; }
@media (max-width: @bp-mobile) {
  .filters { display: block; }
  .filters__panel { width: 100%; }
}
</style>
