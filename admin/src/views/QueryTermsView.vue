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
const newTerm = ref("");

const columns = [
  { prop: "term", label: "Термін" },
  { prop: "support", label: "Бізнес-сайтів" },
  { slot: "protected", label: "Захищений" },
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
async function onToPending(id) {
  try {
    await terms.toPending(id);
    ElMessage.success("Повернуто в кандидати (прибрано з пошуку)");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
// Задача 5C: людський override — ручне додавання + захист від авто-ретайру
async function onManualAdd() {
  const t = newTerm.value.trim();
  if (!t) return;
  try {
    await terms.manualAdd(t);
    ElMessage.success("Додано вручну (захищений, у пошуковому гріді)");
    newTerm.value = "";
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onProtect(id) {
  try {
    await terms.protect(id);
    ElMessage.success("Захищено від авто-ретайру");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}
async function onUnprotect(id) {
  try {
    await terms.unprotect(id);
    ElMessage.success("Захист знято");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, pageItems, page, total, setPage, load, newTerm,
  onApprove, onReject, onUnreject, onToPending, onManualAdd, onProtect, onUnprotect, status });
</script>

<template>
  <div class="query-terms-view">
    <div class="header">
      <h2>Кандидати-терміни пошуку</h2>
      <div class="controls">
        <el-input
          v-model="newTerm"
          placeholder="Додати термін вручну"
          style="width: 220px"
          clearable
          @keyup.enter="onManualAdd"
        />
        <el-button type="primary" @click="onManualAdd">Додати</el-button>
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

    <ResponsiveTable :columns="columns" :rows="pageItems" :loading="loading" :actions-width="320">
      <template #col-protected="{ row }">
        <el-tag v-if="row.protected" type="warning" size="small">Захищений</el-tag>
        <span v-else class="muted">—</span>
      </template>
      <template #actions="{ row }">
        <template v-if="row.status === 'pending'">
          <el-button size="small" type="success" @click="onApprove(row.id)">Затвердити</el-button>
          <el-button size="small" type="danger" @click="onReject(row.id)">Відхилити</el-button>
        </template>
        <el-button v-else-if="row.status === 'rejected'" size="small" @click="onUnreject(row.id)">
          Повернути в кандидати
        </el-button>
        <el-button v-else-if="row.status === 'approved'" size="small" @click="onToPending(row.id)">
          Повернути в кандидати
        </el-button>
        <span v-else>{{ enumLabel(SUGGESTION_STATUSES, row.status) }}</span>
        <el-button v-if="row.protected" size="small" @click="onUnprotect(row.id)">Зняти захист</el-button>
        <el-button v-else size="small" type="warning" @click="onProtect(row.id)">Захистити</el-button>
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
.muted { color: var(--el-text-color-secondary); }
</style>
