<script setup>
import { onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { useApiList } from "@/composables/useApiList";
import { useModerationStore } from "@/stores/moderation";
import * as offers from "@/api/offers";
import { OFFER_STATUSES, OFFER_TYPES } from "@/constants/enums";
import { enumLabel, formatDate, statusTagType, isHttpUrl, supersedeSummary } from "@/utils/format";
import { confirmDelete, confirmAction } from "@/utils/confirm";
import { extractError } from "@/utils/errors";
import DataTableToolbar from "@/components/DataTableToolbar.vue";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const props = defineProps({ fixedStatus: { type: String, default: null } });
const router = useRouter();
const route = useRoute();
const moderation = useModerationStore();

// Main offers page is split into status tabs; the moderation-queue variant
// (fixedStatus set) pins its status and shows no tabs. The active tab lives in the
// URL (?tab=) so it survives an edit round-trip (return-to-origin).
const tab = ref(props.fixedStatus ? "pending_review" : (route.query.tab || "published"));

// Keep the tab in the URL (no remount) and reload — tabbed offers view only.
function onTabChange() {
  if (!props.fixedStatus) router.replace({ query: { ...route.query, tab: tab.value } });
  applyFilters({});
}

const columns = [
  { label: "Заголовок", slot: "title" },
  { prop: "provider", label: "Провайдер" },
  { label: "Тип", slot: "type" },
  { label: "Статус", slot: "status" },
  { label: "Дійсний до", slot: "validUntil" },
  { label: "Джерело", slot: "source", width: 170 },
];

function loader(params) {
  const p = { ...params };
  p.status = props.fixedStatus || tab.value;   // moderation-queue pins; else the active tab drives status
  Object.keys(p).forEach((k) => {
    if (p[k] === "" || p[k] == null) delete p[k];
  });
  return offers.list(p);
}

const { items, total, page, size, loading, filters, load, setPage, applyFilters } =
  useApiList(loader, { type: "", q: "" });

onMounted(load);

async function onPublish(id) {
  try {
    await offers.publish(id);
    ElMessage.success("Опубліковано");
    await load();
    moderation.refresh();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onReject(id) {
  try {
    await offers.reject(id);
    ElMessage.success("Відхилено");
    await load();
    moderation.refresh();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onRestore(id) {
  try {
    await offers.restore(id);
    ElMessage.success("Відновлено");
    await load();
    moderation.refresh();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onBlockHost(id) {
  try {
    await confirmAction("Заблокувати хост цього офера в медіа-блоклісті? Краулер більше не братиме цей сайт.");
  } catch {
    return;
  }
  try {
    const res = await offers.blockHost(id);
    ElMessage.success(`Заблоковано: ${res.host}`);
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onDelete(id) {
  try {
    await confirmDelete();
  } catch {
    return;
  }
  try {
    await offers.remove(id);
    ElMessage.success("Видалено");
    await load();
    moderation.refresh();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

function edit(id) {
  const query = props.fixedStatus
    ? { from: route.name }
    : { from: route.name, tab: tab.value };
  router.push({ name: "offer-edit", params: { id }, query });
}

function pluralZnyzhka(n) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "знижка";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "знижки";
  return "знижок";
}

defineExpose({ onPublish, onReject, onRestore, onDelete, onBlockHost, edit, load, applyFilters, items, tab });
</script>

<template>
  <div class="offers-list">
    <div class="header">
      <h2>{{ fixedStatus ? "Черга модерації" : "Оффери" }}</h2>
      <el-button v-if="!fixedStatus" type="primary" @click="router.push({ name: 'offer-new', query: { from: route.name } })">
        Створити оффер
      </el-button>
    </div>

    <el-tabs v-if="!fixedStatus" v-model="tab" @tab-change="onTabChange">
      <el-tab-pane label="Опубліковані" name="published" />
      <el-tab-pane label="На модерації" name="pending_review" />
      <el-tab-pane label="Відхилені" name="rejected" />
    </el-tabs>

    <DataTableToolbar @search="(q) => applyFilters({ q })">
      <template #filters>
        <el-select
          v-model="filters.type"
          placeholder="Тип"
          clearable
          style="width: 140px"
          @change="applyFilters({})"
        >
          <el-option v-for="t in OFFER_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
      </template>
    </DataTableToolbar>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="280">
      <template #col-title="{ row }">
        <div>{{ row.title }}</div>
        <el-tag v-if="row.status === 'pending_review' && supersedeSummary(row)" size="small" type="warning" style="margin-top: 4px">
          {{ supersedeSummary(row) }}
        </el-tag>
        <el-tag v-if="row.discounts?.length > 1" size="small" style="margin-top: 4px; margin-left: 4px">
          {{ `${row.discounts.length} ${pluralZnyzhka(row.discounts.length)}` }}
        </el-tag>
      </template>
      <template #col-type="{ row }">{{ enumLabel(OFFER_TYPES, row.type) }}</template>
      <template #col-status="{ row }">
        <el-tag :type="statusTagType(row.status)">{{ enumLabel(OFFER_STATUSES, row.status) }}</el-tag>
      </template>
      <template #col-validUntil="{ row }">{{ formatDate(row.valid_until) }}</template>
      <template #col-source="{ row }">
        <el-link v-if="isHttpUrl(row.site_url)" :href="row.site_url" type="primary" target="_blank" rel="noopener noreferrer">Сайт ↗</el-link>
        <el-link v-if="isHttpUrl(row.article_url)" :href="row.article_url" type="primary" target="_blank" rel="noopener noreferrer" style="margin-left: 8px">Стаття ↗</el-link>
        <span v-if="!isHttpUrl(row.site_url) && !isHttpUrl(row.article_url)" style="color: var(--el-text-color-placeholder)">—</span>
      </template>
      <template #actions="{ row }">
        <el-button size="small" @click="edit(row.id)">Редагувати</el-button>
        <el-button v-if="row.status !== 'published'" size="small" type="success" @click="onPublish(row.id)">Опублікувати</el-button>
        <el-button v-if="row.status === 'pending_review'" size="small" type="warning" @click="onReject(row.id)">Відхилити</el-button>
        <el-button v-if="row.status === 'rejected'" size="small" type="success" @click="onRestore(row.id)">Відновити</el-button>
        <el-button
          v-if="(row.status === 'pending_review' || row.status === 'published') && isHttpUrl(row.site_url)"
          size="small" type="danger" plain @click="onBlockHost(row.id)">Заблокувати</el-button>
        <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
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
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
