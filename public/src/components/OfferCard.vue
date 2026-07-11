<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const props = defineProps({ offer: { type: Object, required: true } });
const image = computed(() => props.offer.image_url || placeholderDataUri(props.offer));
</script>

<template>
  <router-link class="card" :to="{ name: 'offer', params: { id: offer.id } }">
    <div class="card__media">
      <img :src="image" alt="" />
      <OfferBadge :offer="offer" class="card__badge" />
    </div>
    <div class="card__body">
      <h3 class="card__title">{{ offer.title }}</h3>
      <div class="card__provider">{{ offer.provider }}</div>
      <div v-if="offer.location" class="card__location">{{ offer.location }}</div>
      <div v-if="offer.target_categories?.length" class="card__tags">
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
    </div>
  </router-link>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.card { display: block; background: @card-bg; border: 1px solid @border; border-radius: @radius; overflow: hidden; color: @text; }
.card:hover { text-decoration: none; box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.card__media { position: relative; }
.card__media img { display: block; width: 100%; height: 180px; object-fit: cover; }
.card__badge { position: absolute; top: 8px; left: 8px; }
.card__body { padding: 12px; }
.card__title { margin: 0 0 4px; font-size: 16px; }
.card__provider { color: @muted; font-size: 14px; }
.card__location { color: @muted; font-size: 13px; margin-top: 4px; }
.card__tags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.tag { font-size: 12px; background: #eef2f7; color: @muted; border-radius: 6px; padding: 1px 6px; }
</style>
