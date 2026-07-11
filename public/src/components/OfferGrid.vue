<script setup>
import OfferCard from "@/components/OfferCard.vue";

defineProps({
  offers: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});
</script>

<template>
  <div class="grid-wrap">
    <p v-if="loading" class="state">Завантаження…</p>
    <p v-else-if="error" class="state state--error">{{ error }}</p>
    <p v-else-if="!offers.length" class="state">Нічого не знайдено. Спробуйте змінити або скинути фільтри.</p>
    <div v-else class="grid">
      <OfferCard v-for="o in offers" :key="o.id" :offer="o" />
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.state { color: @muted; padding: 32px 0; text-align: center; }
.state--error { color: @danger; }
@media (max-width: 900px) { .grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: @bp-mobile) { .grid { grid-template-columns: 1fr; } }
</style>
