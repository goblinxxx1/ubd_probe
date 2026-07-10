<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as sources from "@/api/sources";
import { SOURCE_TYPES } from "@/constants/enums";
import { enumLabel } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

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

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="name" label="Назва" />
      <el-table-column label="Тип">
        <template #default="{ row }">{{ enumLabel(SOURCE_TYPES, row.type) }}</template>
      </el-table-column>
      <el-table-column prop="url_or_handle" label="URL / handle" />
      <el-table-column label="Активне">
        <template #default="{ row }">{{ row.is_active ? "Так" : "Ні" }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">Редагувати</el-button>
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

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
