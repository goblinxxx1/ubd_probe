<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const props = defineProps({ offer: { type: Object, required: true } });
const image = computed(() => props.offer.image_url || placeholderDataUri(props.offer));
const sourceLinks = computed(() =>
  props.offer.links?.length
    ? props.offer.links
    : (props.offer.site_url || props.offer.article_url
        ? [{ site_url: props.offer.site_url, article_url: props.offer.article_url }]
        : [])
);
</script>

<template>
  <div class="card">
    <router-link class="card__nav" :to="{ name: 'offer', params: { id: offer.id } }">
      <div class="card__media">
        <img :src="image" alt="" />
        <OfferBadge :offer="offer" class="card__badge" />
      </div>
      <h3 class="card__title">{{ offer.title }}</h3>
    </router-link>
    <div class="card__body">
      <div class="card__head">
        <div class="card__provider">{{ offer.provider }}</div>
        <img v-if="offer.image_url" class="card__logo" :src="offer.image_url" alt="" />
      </div>
      <div v-if="offer.location" class="card__location">{{ offer.location }}</div>
      <div v-if="sourceLinks.length" class="card__links">
        <template v-for="(l, i) in sourceLinks" :key="i">
          <a v-if="l.site_url" class="card__link" :href="l.site_url"
             target="_blank" rel="noopener">Сайт{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
          <a v-if="l.article_url" class="card__link" :href="l.article_url"
             target="_blank" rel="noopener">Новина{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
        </template>
      </div>
      <div v-if="offer.target_categories?.length" class="card__tags">
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.card { display: block; background: @card-bg; border: 1px solid @border; border-radius: @radius; overflow: hidden; color: @text; }
.card:hover { text-decoration: none; box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.card__media { position: relative; }
.card__media img { display: block; width: 100%; height: 180px; object-fit: cover; }
.card__badge { position: absolute; top: 8px; left: 8px; }
.card__nav { display: block; color: @text; }
.card__nav:hover { text-decoration: none; }
.card__body { padding: 12px; }
.card__title { margin: 0 12px 4px; font-size: 16px; }
.card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card__logo { width: 40px; height: 40px; object-fit: contain; border-radius: 6px; flex: none; }
.card__links { margin-top: 8px; display: flex; gap: 12px; }
.card__link { font-size: 13px; }
.card__provider { color: @muted; font-size: 14px; }
.card__location { color: @muted; font-size: 13px; margin-top: 4px; }
.card__tags { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }
.tag { font-size: 12px; background: #eef2f7; color: @muted; border-radius: 6px; padding: 1px 6px; }
</style>
