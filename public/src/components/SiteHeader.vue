<script setup></script>

<template>
  <header class="site-header">
    <div class="container site-header__inner">
      <router-link :to="{ name: 'offers' }" class="brand">Знижки для <b>УБД</b></router-link>
      <nav class="nav">
        <router-link :to="{ name: 'offers' }" class="nav__link">Оффери</router-link>
      </nav>
    </div>
  </header>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.site-header { background: @header-bg; border-bottom: 1px solid @divider; }
.site-header__inner { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; }
.brand { font-weight: 900; font-size: 19px; letter-spacing: -.3px; color: @text; }
.brand:hover { text-decoration: none; }
.brand b { color: @brand; }
.nav { font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; }
.nav__link { color: @nav-muted; text-decoration: none; display: inline-flex; align-items: center; min-height: 44px; }
.nav__link:hover { color: @text; }
</style>
