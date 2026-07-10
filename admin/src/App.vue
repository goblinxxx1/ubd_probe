<script setup></script>

<template>
  <router-view v-if="$router" />
  <div v-else class="app-shell">UBD Admin</div>
</template>
