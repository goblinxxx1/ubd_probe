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

async function save(kind, form, id = null) {
  if (!form.name || !form.slug) {
    ElMessage.error("Вкажіть назву та slug");
    return;
  }
  try {
    if (id) await api[kind].update(id, { name: form.name, slug: form.slug });
    else await api[kind].create({ name: form.name, slug: form.slug });
    ElMessage.success("Збережено");
    await dictionaries.reload();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function addDraft(kind) {
  await save(kind, drafts[kind]);
  drafts[kind].name = "";
  drafts[kind].slug = "";
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

defineExpose({ save, remove });
</script>

<template>
  <div class="categories-view">
    <h2>Категорії</h2>
    <el-tabs>
      <el-tab-pane label="Для кого">
        <el-table :data="dictionaries.targetCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="140">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="remove('target', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.target.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.target.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('target')">Додати</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="Тематика">
        <el-table :data="dictionaries.offerCategories" style="width: 100%">
          <el-table-column prop="name" label="Назва" />
          <el-table-column prop="slug" label="Slug" />
          <el-table-column label="Дії" width="140">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="remove('offer', row.id)">Видалити</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="add-row">
          <el-input v-model="drafts.offer.name" placeholder="Назва" style="width: 200px" />
          <el-input v-model="drafts.offer.slug" placeholder="slug" style="width: 200px" />
          <el-button type="primary" @click="addDraft('offer')">Додати</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped lang="less">
.add-row { display: flex; gap: 8px; margin-top: 12px; }
</style>
