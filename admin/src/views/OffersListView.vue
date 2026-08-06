<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { useApiList } from "@/composables/useApiList";
import { useModerationStore } from "@/stores/moderation";
import * as offers from "@/api/offers";
import { OFFER_STATUSES, OFFER_TYPES } from "@/constants/enums";
import { enumLabel, formatDate, statusTagType, isHttpUrl, supersedeSummary,
         discountSummary, confidenceTagType, confidenceLabel, signalLabel } from "@/utils/format";
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

const isQueue = !!props.fixedStatus;   // moderation-queue variant gets preview/confidence extras
// Only "Заголовок" gets a 170px desktop minimum (it held the long promo text and was the
// one being crushed); the rest keep fixed widths and "Деталі" stays auto to fill.
const columns = [
  { label: "Заголовок", slot: "title", minWidth: 170 },
  { prop: "provider", label: "Провайдер", width: 130 },
  { label: "Деталі", slot: "details" },
  ...(isQueue ? [{ label: "Довіра", slot: "confidence", width: 200 }] : []),
  { label: "Статус", slot: "status", width: 120 },
  { label: "Дійсний до", slot: "validUntil", width: 120 },
  { label: "Джерело", slot: "source", width: 160 },
];

// Preview renders the offer on the REAL public site (in preview mode, so unpublished
// queue offers show too) — how it will look to end users, with the admin's data.
const PUBLIC_BASE = import.meta.env.VITE_PUBLIC_BASE
  || `${window.location.protocol}//${window.location.hostname}:8080`;

function preview(row) {
  window.open(`${PUBLIC_BASE}/offers/${row.id}?preview=1`, "_blank", "noopener");
}

// --- confidence-assisted client-side sort (within the loaded page) ---
const sortByConfidence = ref(false);
const TIER_RANK = { low: 0, medium: 1, high: 2 };   // problems first when sorting
const displayItems = computed(() => {
  if (!sortByConfidence.value) return items.value;
  return [...items.value].sort((a, b) => {
    const ra = TIER_RANK[a.confidence?.tier] ?? 1;
    const rb = TIER_RANK[b.confidence?.tier] ?? 1;
    return ra - rb;
  });
});

// --- bulk reject (queue only; reversible soft-trash, #12). No bulk publish. ---
const selected = ref([]);
async function onBulkReject() {
  if (!selected.value.length) return;
  try {
    await confirmAction(`Відхилити вибрані оффери (${selected.value.length})? Їх можна відновити зі вкладки «Відхилені».`);
  } catch {
    return;
  }
  try {
    const res = await offers.bulkReject(selected.value.map((r) => r.id));
    if (res.failed?.length) {
      ElMessage.warning(`Відхилено ${res.rejected.length}, не вдалося ${res.failed.length}`);
    } else {
      ElMessage.success(`Відхилено: ${res.rejected.length}`);
    }
    selected.value = [];
    await load();
    moderation.refresh();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

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

defineExpose({ onPublish, onReject, onRestore, onDelete, onBlockHost, preview, edit, load, applyFilters,
               items, tab, selected, onBulkReject, sortByConfidence, displayItems });
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
        <el-checkbox v-if="isQueue" v-model="sortByConfidence" style="margin-left: 8px">
          Спершу низька довіра
        </el-checkbox>
      </template>
    </DataTableToolbar>

    <div v-if="isQueue" class="bulkbar">
      <el-button type="warning" plain :disabled="!selected.length" @click="onBulkReject">
        Відхилити вибрані ({{ selected.length }})
      </el-button>
    </div>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />

    <ResponsiveTable :columns="columns" :rows="displayItems" :loading="loading" :actions-width="300"
                     :selectable="isQueue" @selection-change="selected = $event">
      <template #col-title="{ row }">
        <div>{{ row.title }}</div>
        <el-tag v-if="row.status === 'pending_review' && supersedeSummary(row)" size="small" type="warning" style="margin-top: 4px">
          {{ supersedeSummary(row) }}
        </el-tag>
        <el-tag v-if="row.discounts?.length > 1" size="small" style="margin-top: 4px; margin-left: 4px">
          {{ `${row.discounts.length} ${pluralZnyzhka(row.discounts.length)}` }}
        </el-tag>
      </template>
      <template #col-details="{ row }">
        <div class="details">
          <el-tag size="small" type="info" effect="plain">{{ discountSummary(row) }}</el-tag>
          <el-tag v-for="loc in (row.locations || []).slice(0, 3)" :key="loc" size="small" class="chip">{{ loc }}</el-tag>
          <span v-if="(row.locations || []).length > 3" class="more">+{{ row.locations.length - 3 }}</span>
          <el-tag v-for="c in (row.offer_categories || [])" :key="c.id" size="small" type="success" effect="plain" class="chip">{{ c.name }}</el-tag>
        </div>
      </template>
      <template v-if="isQueue" #col-confidence="{ row }">
        <template v-if="row.confidence">
          <el-tag :type="confidenceTagType(row.confidence.tier)" size="small">
            {{ confidenceLabel(row.confidence.tier) }}
          </el-tag>
          <span class="hostrep" :title="row.confidence.host">
            ✓{{ row.confidence.host_published }} ✕{{ row.confidence.host_rejected }}
          </span>
          <div class="signals">
            <el-tag v-for="s in row.confidence.signals" :key="s" size="small" effect="plain" class="chip">{{ signalLabel(s) }}</el-tag>
          </div>
        </template>
        <span v-else class="more">—</span>
      </template>
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
        <el-button size="small" type="primary" plain @click="preview(row)">Превʼю ↗</el-button>
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
.details { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.details .chip, .signals .chip { margin: 0; }
.details .more, .hostrep, .more { color: var(--el-text-color-secondary); font-size: 12px; }
.hostrep { margin-left: 6px; }
.signals { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.bulkbar { margin: 8px 0; }
</style>
