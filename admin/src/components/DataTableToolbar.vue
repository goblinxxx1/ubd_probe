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
      placeholder="Пошук"
      clearable
      style="width: 220px"
      @keyup.enter="onSearch"
    />
    <el-button @click="onSearch">Знайти</el-button>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }

@media (max-width: @bp-mobile) {
  .toolbar { flex-wrap: wrap; }
  .toolbar :deep(.el-select), .toolbar :deep(.el-input) { width: 100% !important; }
}
</style>
