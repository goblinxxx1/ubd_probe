<script setup></script>

<template>
  <header class="site-header">
    <div class="container">
      <router-link :to="{ name: 'offers' }" class="logo">Знижки для УБД</router-link>
    </div>
  </header>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.site-header { border-bottom: 1px solid @border; background: @bg; }
.logo { font-weight: 700; font-size: 20px; color: @brand; }
</style>
