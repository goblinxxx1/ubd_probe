<script setup>
import { useBreakpoint } from "@/composables/useBreakpoint";

defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  rowKey: { type: String, default: "id" },
  loading: { type: Boolean, default: false },
  actionsWidth: { type: [String, Number], default: undefined },
});
const { isMobile } = useBreakpoint();
</script>

<template>
  <el-table v-if="!isMobile" :data="rows" :row-key="rowKey" v-loading="loading"
            empty-text="Немає даних" style="width: 100%">
    <el-table-column
      v-for="col in columns"
      :key="col.prop || col.slot || col.label"
      :prop="col.prop"
      :label="col.label"
      :width="col.width"
    >
      <template v-if="col.slot" #default="{ row }">
        <slot :name="'col-' + col.slot" :row="row" />
      </template>
    </el-table-column>
    <el-table-column v-if="$slots.actions" label="Дії" :width="actionsWidth">
      <template #default="{ row }"><slot name="actions" :row="row" /></template>
    </el-table-column>
  </el-table>

  <div v-else class="rt-cards" v-loading="loading">
    <p v-if="!rows.length" class="rt-empty">Немає даних</p>
    <div v-for="row in rows" :key="row[rowKey]" class="rt-card">
      <div v-for="col in columns" :key="col.prop || col.slot || col.label" class="rt-cell">
        <span class="rt-label">{{ col.label }}</span>
        <span class="rt-value">
          <slot v-if="col.slot" :name="'col-' + col.slot" :row="row" />
          <template v-else>{{ row[col.prop] }}</template>
        </span>
      </div>
      <div v-if="$slots.actions" class="rt-actions"><slot name="actions" :row="row" /></div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.rt-cards { display: flex; flex-direction: column; gap: 12px; }
.rt-empty { color: @meta-muted; text-align: center; padding: 24px 0; }
.rt-card { border: 1px solid @divider; border-radius: 10px; background: @surface; padding: 12px; }
.rt-cell { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; border-bottom: 1px solid @divider; }
.rt-cell:last-of-type { border-bottom: none; }
.rt-label { color: @meta-muted; font-size: 13px; flex: 0 0 auto; }
.rt-value { text-align: right; word-break: break-word; }
.rt-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
</style>
