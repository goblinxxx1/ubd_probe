<script setup>
defineProps({
  hasMore: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  shown: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
});
const emit = defineEmits(["load"]);
</script>

<template>
  <div v-if="hasMore" class="loadmore">
    <button class="loadmore__btn" type="button" :disabled="loading" @click="emit('load')">
      {{ loading ? "Завантаження…" : "Завантажити ще" }}
    </button>
    <p class="loadmore__meta">Показано {{ shown }} з {{ total }}</p>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.loadmore { display: flex; flex-direction: column; align-items: center; gap: 8px; margin: 24px 0 8px; }
.loadmore__btn {
  padding: 10px 22px; border: 1px solid @border; border-radius: @radius-sm; background: @card-bg;
  color: @text; font-size: 15px; font-weight: 600; cursor: pointer;
}
.loadmore__btn:not(:disabled):hover { border-color: @link; }
.loadmore__btn:disabled { opacity: 0.6; cursor: default; }
.loadmore__meta { color: @muted; font-size: 13px; margin: 0; }
</style>
