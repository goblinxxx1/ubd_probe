<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as sources from "@/api/sources";
import { SOURCE_TYPES } from "@/constants/enums";
import { enumLabel, isHttpUrl } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const columns = [
  { prop: "name", label: "Назва" },
  { label: "Тип", slot: "type" },
  { label: "URL / handle", slot: "ref" },
  { label: "Активне", slot: "active" },
];

const items = ref([]);
const loading = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const form = reactive({ name: "", type: "website", url_or_handle: "", is_active: true });

async function load() {
  loading.value = true;
  try {
    items.value = await sources.list();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function openCreate() {
  editingId.value = null;
  Object.assign(form, { name: "", type: "website", url_or_handle: "", is_active: true });
  dialogVisible.value = true;
}
function openEdit(row) {
  editingId.value = row.id;
  Object.assign(form, { name: row.name, type: row.type, url_or_handle: row.url_or_handle, is_active: row.is_active });
  dialogVisible.value = true;
}
async function save() {
  if (!form.name || !form.url_or_handle) {
    ElMessage.error("Заповніть назву та URL/handle");
    return;
  }
  try {
    if (editingId.value) await sources.update(editingId.value, { ...form });
    else await sources.create({ ...form });
    ElMessage.success("Збережено");
    dialogVisible.value = false;
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
    await sources.remove(id);
    ElMessage.success("Видалено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, load, openCreate, openEdit, save, onDelete, form, editingId });
</script>

<template>
  <div class="sources-view">
    <div class="header">
      <h2>Джерела</h2>
      <el-button type="primary" @click="openCreate">Додати джерело</el-button>
    </div>

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="200">
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
      <template #col-active="{ row }">{{ row.is_active ? "Так" : "Ні" }}</template>
      <template #actions="{ row }">
        <el-button size="small" @click="openEdit(row)">Редагувати</el-button>
        <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
      </template>
    </ResponsiveTable>

    <el-dialog v-model="dialogVisible" :title="editingId ? 'Редагувати джерело' : 'Нове джерело'">
      <el-form label-position="top">
        <el-form-item label="Назва" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Тип">
          <el-select v-model="form.type" style="width: 200px">
            <el-option v-for="t in SOURCE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="URL / handle" required>
          <el-input v-model="form.url_or_handle" />
        </el-form-item>
        <el-form-item label="Активне">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Скасувати</el-button>
        <el-button type="primary" @click="save">Зберегти</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="less">
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
</style>
