<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as crawlerHealth from "@/api/crawlerHealth";
import { extractError } from "@/utils/errors";

const data = ref(null);      // { snapshot, reported_at }
const loading = ref(false);

const snap = computed(() => data.value?.snapshot || null);

const STATUS = {
  healthy: { type: "success", label: "здоровий" },
  cooling: { type: "warning", label: "кулдаун" },
  quarantined: { type: "danger", label: "карантин" },
};

const backendColumns = [
  { prop: "name", label: "Бекенд" },
  { prop: "status", label: "Статус", slot: "status" },
  { prop: "fails", label: "Збоїв" },
  { prop: "cooldown_s", label: "Кулдаун", slot: "cooldown" },
  { prop: "quarantine_s", label: "Карантин", slot: "quarantine" },
];

const healthyCount = computed(
  () => (snap.value?.backends || []).filter((b) => b.status === "healthy").length
);

function fmtDur(s) {
  if (!s || s <= 0) return "—";
  if (s < 60) return `${s}с`;
  if (s < 3600) return `${Math.round(s / 60)}хв`;
  return `${(s / 3600).toFixed(1)}г`;
}

const ageText = computed(() => {
  if (!data.value?.reported_at) return "";
  const ms = Date.now() - Date.parse(data.value.reported_at);
  if (Number.isNaN(ms)) return "";
  const s = Math.max(0, Math.round(ms / 1000));
  return `оновлено ${fmtDur(s)} тому`;
});

async function load() {
  loading.value = true;
  try {
    data.value = await crawlerHealth.get();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

defineExpose({ data, snap, load, healthyCount });
</script>

<template>
  <div class="crawler-health">
    <div class="header">
      <h2>Здоров'я краулера</h2>
      <div class="controls">
        <span class="age" v-if="ageText">{{ ageText }}</span>
        <el-button :loading="loading" @click="load">Оновити</el-button>
      </div>
    </div>

    <el-empty v-if="!snap && !loading" description="Краулер ще не зголосився" />

    <template v-if="snap">
      <el-alert
        v-if="snap.global_backoff_s > 0"
        type="error"
        :closable="false"
        show-icon
        :title="`Глобальний backoff активний: ${fmtDur(snap.global_backoff_s)}`"
        style="margin-bottom: 12px"
      />
      <el-alert
        v-if="healthyCount <= 1"
        type="warning"
        :closable="false"
        show-icon
        :title="`Лишилось здорових бекендів: ${healthyCount} — канал discovery під загрозою`"
        style="margin-bottom: 12px"
      />

      <h3>Пошукові бекенди</h3>
      <el-table :data="snap.backends" size="small" style="width: 100%">
        <el-table-column prop="name" label="Бекенд" />
        <el-table-column label="Статус">
          <template #default="{ row }">
            <el-tag :type="(STATUS[row.status] || {}).type || 'info'" disable-transitions>
              {{ (STATUS[row.status] || {}).label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="fails" label="Збоїв" width="90" />
        <el-table-column label="Кулдаун" width="110">
          <template #default="{ row }">{{ fmtDur(row.cooldown_s) }}</template>
        </el-table-column>
        <el-table-column label="Карантин" width="110">
          <template #default="{ row }">{{ fmtDur(row.quarantine_s) }}</template>
        </el-table-column>
      </el-table>

      <div class="cards">
        <div class="card">
          <div class="card-title">Фрази запитів</div>
          <div class="metric">{{ snap.phrases.tracked }} <small>відстежено</small></div>
          <div class="sub">
            <el-tag type="success" size="small" disable-transitions>{{ snap.phrases.productive }} продуктивних</el-tag>
            <el-tag :type="snap.phrases.starved > 0 ? 'danger' : 'info'" size="small" disable-transitions>
              {{ snap.phrases.starved }} задушених
            </el-tag>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Recall</div>
          <div class="metric">{{ snap.recall.grid_cursor }} <small>курсор гріда</small></div>
          <div class="sub">{{ snap.recall.cache_entries }} записів кешу</div>
        </div>
      </div>

      <h3>Шум-хости (топ)</h3>
      <el-table :data="snap.noise_hosts" size="small" style="width: 100%">
        <el-table-column prop="host" label="Хост" />
        <el-table-column prop="count" label="Захоплень" width="130" />
      </el-table>
    </template>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.controls { display: flex; align-items: center; gap: 12px; }
.age { color: #909399; font-size: 13px; }
h3 { margin: 20px 0 8px; }
.cards { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 16px; }
.card { flex: 1 1 220px; border: 1px solid var(--el-border-color, #dcdfe6); border-radius: 8px; padding: 14px 16px; }
.card-title { color: #909399; font-size: 13px; margin-bottom: 6px; }
.metric { font-size: 24px; font-weight: 600; }
.metric small { font-size: 13px; font-weight: 400; color: #909399; }
.sub { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
