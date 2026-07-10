<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as users from "@/api/users";
import { ADMIN_ROLES } from "@/constants/enums";
import { enumLabel, formatDate } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

const items = ref([]);
const loading = ref(false);
const form = reactive({ email: "", password: "", role: "moderator" });

async function load() {
  loading.value = true;
  try {
    items.value = await users.list();
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function create() {
  if (!form.email || !form.password) {
    ElMessage.error("Вкажіть email і пароль");
    return;
  }
  try {
    await users.create({ email: form.email, password: form.password, role: form.role });
    ElMessage.success("Створено");
    Object.assign(form, { email: "", password: "", role: "moderator" });
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onDelete(id) {
  try {
    await confirmDelete("Видалити цього адміністратора?");
  } catch {
    return;
  }
  try {
    await users.remove(id);
    ElMessage.success("Видалено");
    await load();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ items, form, load, create, onDelete });
</script>

<template>
  <div class="admin-users-view">
    <h2>Адміністратори</h2>

    <el-table :data="items" v-loading="loading" style="width: 100%">
      <el-table-column prop="email" label="Email" />
      <el-table-column label="Роль">
        <template #default="{ row }">{{ enumLabel(ADMIN_ROLES, row.role) }}</template>
      </el-table-column>
      <el-table-column label="Створено">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="Дії" width="140">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-form class="create-form" :inline="true">
      <el-form-item label="Email">
        <el-input v-model="form.email" type="email" />
      </el-form-item>
      <el-form-item label="Пароль">
        <el-input v-model="form.password" type="password" />
      </el-form-item>
      <el-form-item label="Роль">
        <el-select v-model="form.role" style="width: 160px">
          <el-option v-for="r in ADMIN_ROLES" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="create">Додати</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="less">
.create-form { margin-top: 16px; }
</style>
