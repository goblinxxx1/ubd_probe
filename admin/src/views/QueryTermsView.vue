<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as terms from "@/api/queryTerms";
import { SUGGESTION_STATUSES } from "@/constants/enums";
import { enumLabel } from "@/utils/format";
import { extractError } from "@/utils/errors";
import { confirmAction } from "@/utils/confirm";
import { useClientPagination } from "@/composables/useClientPagination";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const { page, size, total, pageItems, setPage } = useClientPagination(items, 20);
const loading = ref(false);
const status = ref("pending");
const newTerm = ref("");
const selected = ref([]);

const columns = [
  { prop: "term", label: "Термін" },
  { prop: "support", label: "Бізнес-сайтів" },
  { slot: "protected", label: "Закріплено" },
];

async function load() {
  loading.value = true;
  selected.value = [];            // drop stale selection on reload / tab switch
  try {
    items.value = await terms.list({ status: status.value });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

// Масові дії — дзеркало рядкових. `confirm` (текст) вимагає підтвердження на
// незворотні-по-суті переходи (reject, повернення з гріду).
async function runBulk(action, confirm = null) {
  if (!selected.value.length) return;
  if (confirm) {
    try { await confirmAction(confirm); } catch { return; }
  }
  try {
    const res = await terms.bulk(selected.value.map((r) => r.id), action);
    if (res.failed?.length) {
      ElMessage.warning(`Готово: ${res.done.length}, помилок: ${res.failed.length}`);
    } else {
      ElMessage.success(`Готово: ${res.done.length}`);
    }
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

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
    ElMessage.success("Додано вручну (закріплено в пошуку)");
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

defineExpose({ items, pageItems, page, total, setPage, load, newTerm, selected, runBulk,
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

    <div class="bulkbar">
      <span class="sel-count">Вибрано: {{ selected.length }}</span>
      <template v-if="status === 'pending'">
        <el-button size="small" type="success" plain :disabled="!selected.length"
                   @click="runBulk('approve')">Затвердити вибрані</el-button>
        <el-button size="small" type="danger" plain :disabled="!selected.length"
                   @click="runBulk('reject', `Відхилити вибрані терміни (${selected.length})?`)">
          Відхилити вибрані</el-button>
      </template>
      <el-button v-else-if="status === 'approved'" size="small" plain :disabled="!selected.length"
                 @click="runBulk('to_pending', `Повернути вибрані в кандидати (${selected.length})? Їх приберуть з пошукового гріду.`)">
        Повернути в кандидати</el-button>
      <el-button v-else-if="status === 'rejected'" size="small" plain :disabled="!selected.length"
                 @click="runBulk('to_pending', `Повернути вибрані в кандидати (${selected.length})?`)">
        Повернути в кандидати</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" type="warning" plain :disabled="!selected.length"
                 @click="runBulk('protect')">Закріпити вибрані</el-button>
      <el-button size="small" plain :disabled="!selected.length"
                 @click="runBulk('unprotect')">Відкріпити вибрані</el-button>
    </div>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />

    <ResponsiveTable :columns="columns" :rows="pageItems" :loading="loading" :actions-width="320"
                     selectable @selection-change="selected = $event">
      <template #col-protected="{ row }">
        <el-tag v-if="row.protected" type="warning" size="small">Закріплено</el-tag>
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
        <el-button v-if="row.protected" size="small" @click="onUnprotect(row.id)"
                   title="Відкріпити: дозволити авто-керування — термін може ретайритись, якщо перестане давати нові офери">Відкріпити</el-button>
        <el-button v-else size="small" type="warning" @click="onProtect(row.id)"
                   title="Закріпити в пошуку: планувальник ЗАВЖДИ шукатиме цей термін і не прибиратиме його автоматично, навіть якщо тимчасово без нових оферів">Закріпити</el-button>
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
.bulkbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.sel-count { color: var(--el-text-color-secondary); font-size: 13px; margin-right: 4px; }
.muted { color: var(--el-text-color-secondary); }
</style>
