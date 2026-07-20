<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { formatDate } from "@/utils/format";
import OfferBadge from "@/components/OfferBadge.vue";

const route = useRoute();
const offer = ref(null);
const loading = ref(true);
const notFound = ref(false);

const period = computed(() => {
  if (!offer.value) return "";
  const from = formatDate(offer.value.valid_from);
  const to = formatDate(offer.value.valid_until);
  if (from && to) return `${from} – ${to}`;
  return from || to || "";
});

onMounted(async () => {
  try {
    offer.value = await offersApi.get(route.params.id);
  } catch {
    notFound.value = true;
  } finally {
    loading.value = false;
  }
});

const sourceLinks = computed(() => {
  const o = offer.value;
  if (!o) return [];
  if (o.links?.length) return o.links;
  return o.site_url || o.article_url
    ? [{ site_url: o.site_url, article_url: o.article_url }]
    : [];
});

defineExpose({ offer, loading, notFound });
</script>

<template>
  <div class="container detail">
    <p v-if="loading" class="state">Завантаження…</p>

    <div v-else-if="notFound" class="state">
      <h1>Оффер не знайдено</h1>
      <router-link :to="{ name: 'offers' }">← до списку</router-link>
    </div>

    <article v-else>
      <router-link :to="{ name: 'offers' }" class="detail__back">← до списку</router-link>

      <div class="detail__head">
        <h1 class="detail__provider">{{ offer.provider }}</h1>
        <img v-if="offer.image_url" class="detail__photo" :src="offer.image_url" :alt="offer.provider" />
      </div>

      <div class="detail__discount">
        <OfferBadge :offer="offer" />
        <span v-if="offer.title" class="detail__dtext">{{ offer.title }}</span>
      </div>

      <p v-if="offer.description" class="detail__desc">{{ offer.description }}</p>

      <div v-if="offer.target_categories?.length" class="detail__whom">
        <div class="detail__whom-label">Для кого</div>
        <div class="detail__chips">
          <span v-for="t in offer.target_categories" :key="t.id" class="chip">{{ t.name }}</span>
        </div>
      </div>

      <div v-if="offer.offer_categories?.length" class="detail__row">
        <span class="detail__label">Тематика:</span>
        <span v-for="c in offer.offer_categories" :key="c.id" class="chip chip--light">{{ c.name }}</span>
      </div>
      <div v-if="offer.location" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.location }}</div>
      <div v-if="period" class="detail__row"><span class="detail__label">Діє:</span> {{ period }}</div>
      <div v-for="(l, i) in sourceLinks" :key="i" class="detail__row">
        <span class="detail__label">Джерело{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}:</span>
        <a v-if="l.site_url" :href="l.site_url" target="_blank" rel="noopener">Сайт</a>
        <a v-if="l.article_url" :href="l.article_url" target="_blank" rel="noopener" style="margin-left:8px">Сторінка новини</a>
      </div>
    </article>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.detail__back { display: inline-block; margin-bottom: 16px; color: @link; }
.detail__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.detail__provider { margin: 0; font-weight: 900; font-size: 38px; line-height: .95; letter-spacing: -.5px; color: @text; overflow-wrap: anywhere; min-width: 0; }
.detail__photo { width: 40px; height: 40px; flex: none; object-fit: cover; border-radius: 9px; }
.detail__discount { display: flex; align-items: center; gap: 10px; margin: 14px 0; }
.detail__dtext { font-size: 14px; }
.detail__desc { line-height: 1.55; color: @desc-muted; margin: 0 0 16px; }
.detail__whom {
  background: @whom-bg; border: 1px solid @whom-border; border-radius: 8px; padding: 9px 11px; margin-bottom: 14px;
  display: inline-block;
}
.detail__whom-label { font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px; color: @meta-muted; font-weight: 700; margin-bottom: 6px; }
.detail__chips { display: flex; flex-wrap: wrap; gap: 5px; }
.chip { font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: @chip-bg; color: @chip-text; }
.chip--light { background: @whom-bg; color: @meta-muted; border: 1px solid @whom-border; margin-right: 4px; }
.detail__row { margin: 8px 0; }
.detail__label { color: @meta-muted; margin-right: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: .5px; }
.state { text-align: center; padding: 48px 0; color: @meta-muted; }
</style>
