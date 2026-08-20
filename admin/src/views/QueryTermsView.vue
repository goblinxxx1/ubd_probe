<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as terms from "@/api/queryTerms";
import { SUGGESTION_STATUSES } from "@/constants/enums";
import { enumLabel } from "@/utils/format";
import { extractError } from "@/utils/errors";
import { useClientPagination } from "@/composables/useClientPagination";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const { page, size, total, pageItems, setPage } = useClientPagination(items, 20);
const loading = ref(false);
const status = ref("pending");

const columns = [
  { prop: "term", label: "Термін" },
  { prop: "support", label: "Бізнес-сайтів" },
];

async function load() {
  loading.value = true;
  try {
    items.value = await terms.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onApprove(id) {
  try {
    await terms.approve(id);
    ElMessage.success("Затверджено (додано в пошуковий грід)");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onReject(id) {
  try {
    await terms.reject(id);
    ElMessage.success("Відхилено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onUnreject(id) {
  try {
    await terms.unreject(id);
    ElMessage.success("Повернуто в кандидати");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, pageItems, page, total, setPage, load, onApprove, onReject, onUnreject, status });
</script>

<template>
  <div class="query-terms-view">
    <div class="header">
      <h2>Кандидати-терміни пошуку</h2>
      <div class="controls">
        <el-select v-model="status" style="width: 160px" @change="load">
          <el-option v-for="s in SUGGESTION_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
      </div>
    </div>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />

    <ResponsiveTable :columns="columns" :rows="pageItems" :loading="loading" :actions-width="220">
      <template #actions="{ row }">
        <template v-if="row.status === 'pending'">
          <el-button size="small" type="success" @click="onApprove(row.id)">Затвердити</el-button>
          <el-button size="small" type="danger" @click="onReject(row.id)">Відхилити</el-button>
        </template>
        <el-button v-else-if="row.status === 'rejected'" size="small" @click="onUnreject(row.id)">
          Повернути в кандидати
        </el-button>
        <span v-else>{{ enumLabel(SUGGESTION_STATUSES, row.status) }}</span>
      </template>
    </ResponsiveTable>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
