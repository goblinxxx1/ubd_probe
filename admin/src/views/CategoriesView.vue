<script setup>
import { reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import * as categories from "@/api/categories";
import { useDictionariesStore } from "@/stores/dictionaries";
import { confirmDelete } from "@/utils/confirm";
import { extractError } from "@/utils/errors";

const dictionaries = useDictionariesStore();
onMounted(() => dictionaries.load());

const api = {
  target: { create: categories.createTarget, update: categories.updateTarget, remove: categories.removeTarget },
  offer: { create: categories.createOffer, update: categories.updateOffer, remove: categories.removeOffer },
};

const drafts = reactive({
  target: { name: "", slug: "" },
  offer: { name: "", slug: "" },
});

const editingId = reactive({ target: null, offer: null });

function startEdit(kind, row) {
  editingId[kind] = row.id;
  drafts[kind].name = row.name;
  drafts[kind].slug = row.slug;
}

function cancelEdit(kind) {
  editingId[kind] = null;
  drafts[kind].name = "";
  drafts[kind].slug = "";
}

async function save(kind, form, id = null) {
  if (!form.name || !form.slug) {
    ElMessage.error("Вкажіть назву та slug");
    return false;
  }
  try {
    if (id) await api[kind].update(id, { name: form.name, slug: form.slug });
    else await api[kind].create({ name: form.name, slug: form.slug });
    ElMessage.success("Збережено");
    await dictionaries.reload();
    return true;
  } catch (e) {
    ElMessage.error(extractError(e));
    return false;
  }
}

async function addDraft(kind) {
  const ok = await save(kind, drafts[kind], editingId[kind]);
  if (ok) {
    editingId[kind] = null;
    drafts[kind].name = "";
    drafts[kind].slug = "";
  }
}

async function remove(kind, id) {
  try {
    await confirmDelete();
  } catch {
    return;
  }
  try {
    await api[kind].remove(id);
    ElMessage.success("Видалено");
    await dictionaries.reload();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ save, remove, startEdit, editingId });
</script>

<template>
  <div class="categories-view">
    <h2>Категорії</h2>
    <el-tabs>
      <el-tab-pane label="Для кого">
        <el-table :data="dictionaries.targetCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="200">
            <template #default="{ row }">
              <el-button size="small" @click="startEdit('target', row)">Редагувати</el-button>
              <el-button size="small" type="danger" @click="remove('target', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.target.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.target.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('target')">{{ editingId.target ? "Зберегти" : "Додати" }}</el-button>
          <el-button v-if="editingId.target" @click="cancelEdit('target')">Скасувати</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Тематика">
        <el-table :data="dictionaries.offerCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="200">
            <template #default="{ row }">
              <el-button size="small" @click="startEdit('offer', row)">Редагувати</el-button>
              <el-button size="small" type="danger" @click="remove('offer', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.offer.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.offer.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('offer')">{{ editingId.offer ? "Зберегти" : "Додати" }}</el-button>
          <el-button v-if="editingId.offer" @click="cancelEdit('offer')">Скасувати</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped lang="less">
.add-row { display: flex; gap: 8px; margin-top: 12px; }
</style>
