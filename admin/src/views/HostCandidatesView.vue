<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as hosts from "@/api/hostCandidates";
import { SUGGESTION_STATUSES } from "@/constants/enums";
import { enumLabel, isHttpUrl } from "@/utils/format";
import { extractError } from "@/utils/errors";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const loading = ref(false);
const status = ref("pending");

const columns = [
  { prop: "host", label: "Хост" },
  { label: "Медіа", slot: "media" },
  { label: "Агрегатор", slot: "aggr" },
  { prop: "support", label: "Support" },
  { label: "Приклади", slot: "samples" },
];

async function load() {
  loading.value = true;
  try {
    items.value = await hosts.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onApprove(id) {
  try {
    await hosts.approve(id);
    ElMessage.success("Заблоковано (додано у медіа/агрегатор-список)");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onReject(id) {
  try {
    await hosts.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, onApprove, onReject, status });
</script>

<template>
  <div class="host-candidates-view">
    <div class="header">
      <h2>Кандидати в медіа/агрегатор-блоклист</h2>
      <el-select v-model="status" style="width: 160px" @change="load">
        <el-option v-for="s in SUGGESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
    </div>

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="220">
      <template #col-media="{ row }">{{ (row.media_ratio * 100).toFixed(0) }}%</template>
      <template #col-aggr="{ row }">{{ (row.aggregator_ratio * 100).toFixed(0) }}%</template>
      <template #col-samples="{ row }">
        <div v-for="u in row.sample_urls || []" :key="u">
          <el-link v-if="isHttpUrl(u)" :href="u" type="primary" target="_blank" rel="noopener noreferrer">{{ u }}</el-link>
          <span v-else>{{ u }}</span>
        </div>
      </template>
      <template #actions="{ row }">
        <template v-if="row.status === 'pending'">
          <el-button size="small" type="success" @click="onApprove(row.id)">Заблокувати</el-button>
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
