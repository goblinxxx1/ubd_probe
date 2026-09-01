<script setup>
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as blocklist from "@/api/blocklist";
import { isHttpUrl } from "@/utils/format";
import { extractError } from "@/utils/errors";
import { useClientPagination } from "@/composables/useClientPagination";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const { page, size, total, pageItems, setPage } = useClientPagination(items, 20);
const loading = ref(false);
const newHost = ref("");

const columns = [
  { prop: "host", label: "Хост" },
  { label: "Приклади", slot: "samples" },
];

async function load() {
  loading.value = true;
  try {
    items.value = await blocklist.list();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function onUnblock(id) {
  try {
    await blocklist.unblock(id);
    ElMessage.success("Розблоковано (прибрано з блоклиста)");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onAdd() {
  const host = newHost.value.trim();
  if (!host) return;
  try {
    await blocklist.create(host);
    ElMessage.success("Хост заблоковано");
    newHost.value = "";
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, pageItems, page, total, size, setPage, load, onUnblock, onAdd, newHost });
</script>

<template>
  <div class="blocklist-view">
    <div class="header">
      <h2>Медіа-блоклист</h2>
      <div class="controls">
        <el-input
          v-model="newHost"
          placeholder="Заблокувати хост (напр. veteran.com.ua)"
          clearable
          style="width: 320px"
          @keyup.enter="onAdd"
        />
        <el-button type="danger" @click="onAdd">Заблокувати хост</el-button>
      </div>
    </div>

    <el-pagination
      layout="prev, pager, next"
      :total="total"
      :page-size="size"
      :current-page="page"
      @current-change="setPage"
    />

    <ResponsiveTable :columns="columns" :rows="pageItems" :loading="loading" :actions-width="160">
      <template #col-samples="{ row }">
        <div v-for="u in row.sample_urls || []" :key="u">
          <el-link v-if="isHttpUrl(u)" :href="u" type="primary" target="_blank" rel="noopener noreferrer">{{ u }}</el-link>
          <span v-else>{{ u }}</span>
        </div>
      </template>
      <template #actions="{ row }">
        <el-button size="small" type="warning" @click="onUnblock(row.id)">Розблокувати</el-button>
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
