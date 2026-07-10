<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useApiList } from "@/composables/useApiList";
import * as offers from "@/api/offers";
import { OFFER_STATUSES, OFFER_TYPES } from "@/constants/enums";
import { enumLabel, formatDate, statusTagType } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";
import DataTableToolbar from "@/components/DataTableToolbar.vue";

const props = defineProps({ fixedStatus: { type: String, default: null } });
const router = useRouter();

function loader(params) {
  const p = { ...params };
  if (props.fixedStatus) p.status = props.fixedStatus;
  Object.keys(p).forEach((k) => {
    if (p[k] === "" || p[k] == null) delete p[k];
  });
  return offers.list(p);
}

const { items, total, page, size, loading, filters, load, setPage, applyFilters } =
  useApiList(loader, { status: "", type: "", q: "" });

onMounted(load);

async function onPublish(id) {
  try {
    await offers.publish(id);
    ElMessage.success("Опубліковано");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onReject(id) {
  try {
    await offers.reject(id);
    ElMessage.success("Відхилено");
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
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

function edit(id) {
  router.push({ name: "offer-edit", params: { id } });
}

defineExpose({ onPublish, onReject, onDelete, load, applyFilters, items });
</script>

<template>
  <div class="offers-list">
    <div class="header">
      <h2>{{ fixedStatus ? "Черга модерації" : "Оффери" }}</h2>
      <el-button v-if="!fixedStatus" type="primary" @click="router.push({ name: 'offer-new' })">
        Створити оффер
      </el-button>
    </div>

    <DataTableToolbar @search="(q) => applyFilters({ q })">
      <template #filters>
        <el-select
          v-if="!fixedStatus"
          v-model="filters.status"
          placeholder="Статус"
          clearable
          style="width: 160px"
          @change="applyFilters({})"
        >
          <el-option v-for="s in OFFER_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
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

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="title" label="Заголовок" />
      <el-table-column prop="provider" label="Провайдер" />
      <el-table-column label="Тип">
        <template #default="{ row }">{{ enumLabel(OFFER_TYPES, row.type) }}</template>
      </el-table-column>
      <el-table-column label="Статус">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)">{{ enumLabel(OFFER_STATUSES, row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Дійсний до">
        <template #default="{ row }">{{ formatDate(row.valid_until) }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="edit(row.id)">Редагувати</el-button>
          <el-button v-if="row.status !== 'published'" size="small" type="success" @click="onPublish(row.id)">
            Опублікувати
          </el-button>
          <el-button v-if="row.status === 'pending_review'" size="small" type="warning" @click="onReject(row.id)">
            Відхилити
          </el-button>
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

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
