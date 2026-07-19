<script setup>
import { computed, ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import * as offers from "@/api/offers";
import { useBreakpoint } from "@/composables/useBreakpoint";

const auth = useAuthStore();
const router = useRouter();
const isSuperAdmin = computed(() => auth.isSuperAdmin);
const pendingCount = ref(0);
const { isTablet } = useBreakpoint();
const drawerOpen = ref(false);
defineExpose({ drawerOpen });

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
    <aside class="sidebar" :class="{ 'sidebar--open': drawerOpen }">
      <h1 class="logo">UBD</h1>
      <nav>
        <router-link :to="{ name: 'offers' }" @click="drawerOpen = false">Оффери</router-link>
        <router-link :to="{ name: 'moderation' }" @click="drawerOpen = false">
          <el-badge :value="pendingCount" :hidden="!pendingCount">Черга модерації</el-badge>
        </router-link>
        <router-link :to="{ name: 'sources' }" @click="drawerOpen = false">Джерела</router-link>
        <router-link :to="{ name: 'suggested-sources' }" @click="drawerOpen = false">Запропоновані джерела</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'categories' }" @click="drawerOpen = false">Категорії</router-link>
        <router-link v-if="isSuperAdmin" :to="{ name: 'users' }" @click="drawerOpen = false">Адміни</router-link>
      </nav>
    </aside>
    <div v-if="drawerOpen" class="sidebar__backdrop" @click="drawerOpen = false"></div>
    <div class="main">
      <header class="topbar">
        <button class="hamburger" aria-label="Меню" @click="drawerOpen = !drawerOpen">☰</button>
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
.sidebar { width: @sidebar-width; background: @surface; border-right: 1px solid @divider; padding: 16px 12px; }
.logo { font-family: "UAF Memory", system-ui, sans-serif; font-weight: @heading-weight; font-size: 26px; color: @brand; margin: 0 0 16px; letter-spacing: -.3px; }
.sidebar nav { display: flex; flex-direction: column; gap: 4px; }
.sidebar nav a { font-family: "UAF Memory", system-ui, sans-serif; font-weight: 500; text-decoration: none; color: @nav-muted; padding: 8px 10px; border-radius: 8px; border-left: 3px solid transparent; }
.sidebar nav a:hover { color: @text; background: @cream; }
.sidebar nav a.router-link-active { color: @link; background: @cream; border-left-color: @link; }
.sidebar nav a:focus-visible { outline: 2px solid @dark; outline-offset: 2px; }
.main { flex: 1; display: flex; flex-direction: column; background: @bg; }
.topbar { display: flex; justify-content: flex-end; align-items: center; gap: 12px; padding: 10px 16px; background: @surface; border-bottom: 1px solid @divider; }
.topbar .role { color: @meta-muted; font-size: 13px; text-transform: uppercase; letter-spacing: .3px; }
.content { padding: 20px; overflow: auto; }
.hamburger { display: none; background: none; border: none; font-size: 22px; cursor: pointer; color: @text; margin-right: auto; }
@media (max-width: @bp-tablet) {
  .hamburger { display: block; }
  .sidebar {
    position: fixed; z-index: 1001; top: 0; left: 0; height: 100%;
    transform: translateX(-100%); transition: transform .2s ease;
  }
  .sidebar--open { transform: translateX(0); }
  .sidebar__backdrop { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.45); }
}
</style>
