<script setup>
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import * as offers from "@/api/offers";

const auth = useAuthStore();
const router = useRouter();
const isSuperAdmin = computed(() => auth.isSuperAdmin);
const pendingCount = ref(0);

onMounted(async () => {
  try {
    const result = await offers.list({ status: "pending_review", size: 1 });
    pendingCount.value = result?.total ?? 0;
  } catch {
    // badge is non-critical — ignore errors silently
  }
});

function logout() {
  auth.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div class="admin-layout">
    <aside class="sidebar">
      <h1 class="logo">UBD</h1>
      <nav>
        <router-link :to="{ name: 'offers' }">Оффери</router-link>
        <router-link :to="{ name: 'moderation' }">
          <el-badge :value="pendingCount" :hidden="!pendingCount">Черга модерації</el-badge>
        </router-link>
        <router-link :to="{ name: 'sources' }">Джерела</router-link>
        <router-link :to="{ name: 'suggested-sources' }">Запропоновані джерела</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'categories' }">Категорії</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'users' }">Адміни</router-link>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <span class="role">{{ auth.role }}</span>
        <el-button size="small" @click="logout">Вийти</el-button>
      </header>
      <main class="content"><router-view /></main>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.admin-layout { display: flex; height: 100%; }
.sidebar { width: @sidebar-width; background: #f5f7fa; padding: 12px; }
.sidebar nav { display: flex; flex-direction: column; gap: 8px; }
.main { flex: 1; display: flex; flex-direction: column; }
.topbar { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid #eee; }
.content { padding: 16px; overflow: auto; }
</style>
