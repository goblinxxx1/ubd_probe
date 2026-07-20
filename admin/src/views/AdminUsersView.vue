<script setup>
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as users from "@/api/users";
import { ADMIN_ROLES } from "@/constants/enums";
import { enumLabel, formatDate } from "@/utils/format";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";
import ResponsiveTable from "@/components/ResponsiveTable.vue";

const items = ref([]);
const loading = ref(false);
const form = reactive({ email: "", password: "", role: "moderator" });

const columns = [
  { prop: "email", label: "Email" },
  { label: "Роль", slot: "role" },
  { label: "Створено", slot: "created" },
];

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
  if (form.password.length < 8) {
    ElMessage.error("Пароль має містити щонайменше 8 символів");
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

    <ResponsiveTable :columns="columns" :rows="items" :loading="loading" :actions-width="140">
      <template #col-role="{ row }">{{ enumLabel(ADMIN_ROLES, row.role) }}</template>
      <template #col-created="{ row }">{{ formatDate(row.created_at) }}</template>
      <template #actions="{ row }">
        <el-button size="small" type="danger" @click="onDelete(row.id)">Видалити</el-button>
      </template>
    </ResponsiveTable>

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
