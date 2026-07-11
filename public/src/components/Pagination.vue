<script setup>
import { computed } from "vue";

const props = defineProps({
  total: { type: Number, default: 0 },
  size: { type: Number, default: 12 },
  page: { type: Number, default: 1 },
});
const emit = defineEmits(["change"]);

const totalPages = computed(() => Math.ceil(props.total / props.size));

function go(p) {
  if (p >= 1 && p <= totalPages.value && p !== props.page) emit("change", p);
}
</script>

<template>
  <nav v-if="totalPages > 1" class="pagination">
    <button data-test="prev" class="btn" :disabled="page <= 1" @click="go(page - 1)">← Назад</button>
    <span class="pagination__label">Сторінка {{ page }} з {{ totalPages }}</span>
    <button data-test="next" class="btn" :disabled="page >= totalPages" @click="go(page + 1)">Далі →</button>
  </nav>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.pagination { display: flex; align-items: center; justify-content: center; gap: 12px; margin: 24px 0; }
.pagination__label { color: @muted; font-size: 14px; }
.btn { padding: 8px 14px; border: 1px solid @border; border-radius: 8px; background: @bg; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: default; }
</style>
