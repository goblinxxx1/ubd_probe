<script setup>
import { ref } from "vue";

const emit = defineEmits(["search"]);
const q = ref("");

function onSearch() {
  emit("search", q.value);
}

defineExpose({ q });
</script>

<template>
  <div class="toolbar">
    <slot name="filters" />
    <el-input
      v-model="q"
      class="toolbar__search"
      placeholder="Пошук"
      clearable
      @keyup.enter="onSearch"
    />
    <el-button @click="onSearch">Знайти</el-button>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.toolbar__search { width: 220px; }

@media (max-width: @bp-mobile) {
  .toolbar { flex-wrap: wrap; }
  .toolbar__search { width: 100%; }
  // Filter selects are slotted in by the parent view with inline widths
  // (e.g. style="width:160px"); an inline style can only be beaten with !important.
  .toolbar :deep(.el-select) { width: 100% !important; }
}
</style>
