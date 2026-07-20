<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as suggested from "@/api/suggestedSources";
import { SOURCE_TYPES, SUGGESTION_STATUSES } from "@/constants/enums";
import { enumLabel, isHttpUrl } from "@/utils/format";
import { extractError } from "@/utils/errors";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const loading = ref(false);
const status = ref("pending");

const columns = [
  { prop: "name", label: "Назва" },
  { label: "Тип", slot: "type" },
  { label: "URL / handle", slot: "ref" },
  { prop: "discovery_note", label: "Нотатка" },
];

async function load() {
  loading.value = true;
  try {
    items.value = await suggested.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onApprove(id) {
  try {
    await suggested.approve(id);
    ElMessage.success("Схвалено — джерело створено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onReject(id) {
  try {
    await suggested.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, onApprove, onReject, status });
</script>

<template>
  <div class="suggested-view">
    <div class="header">
      <h2>Запропоновані джерела</h2>
      <el-select v-model="status" style="width: 160px" @change="load">
        <el-option v-for="s in SUGGESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
    </div>

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="220">
      <template #col-type="{ row }">{{ enumLabel(SOURCE_TYPES, row.type) }}</template>
      <template #col-ref="{ row }">
        <el-link
          v-if="isHttpUrl(row.url_or_handle)"
          :href="row.url_or_handle"
          type="primary"
          target="_blank"
          rel="noopener noreferrer"
        >{{ row.url_or_handle }}</el-link>
        <span v-else>{{ row.url_or_handle }}</span>
      </template>
      <template #actions="{ row }">
        <template v-if="row.status === 'pending'">
          <el-button size="small" type="success" @click="onApprove(row.id)">Схвалити</el-button>
          <el-button size="small" type="danger" @click="onReject(row.id)">Відхилити</el-button>
        </template>
        <span v-else>{{ enumLabel(SUGGESTION_STATUSES, row.status) }}</span>
      </template>
    </ResponsiveTable>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
