<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import * as offersApi from "@/api/offers";
import { formatDate } from "@/utils/format";
import { placeholderDataUri } from "@/utils/placeholder";
import OfferBadge from "@/components/OfferBadge.vue";

const route = useRoute();
const offer = ref(null);
const loading = ref(true);
const notFound = ref(false);

const image = computed(() =>
  offer.value ? offer.value.image_url || placeholderDataUri(offer.value) : ""
);
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
      <router-link :to="{ name: 'offers' }" class="back">← до списку</router-link>
      <div class="detail__media">
        <img :src="image" alt="" />
        <OfferBadge :offer="offer" class="detail__badge" />
      </div>
      <h1>{{ offer.title }}</h1>
      <div class="detail__provider">{{ offer.provider }}</div>
      <p v-if="offer.description" class="detail__desc">{{ offer.description }}</p>

      <div v-if="offer.target_categories?.length" class="detail__row">
        <span class="detail__label">Для кого:</span>
        <span v-for="t in offer.target_categories" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
      <div v-if="offer.offer_categories?.length" class="detail__row">
        <span class="detail__label">Тематика:</span>
        <span v-for="c in offer.offer_categories" :key="c.id" class="tag">{{ c.name }}</span>
      </div>
      <div v-if="offer.location" class="detail__row"><span class="detail__label">Локація:</span> {{ offer.location }}</div>
      <div v-if="period" class="detail__row"><span class="detail__label">Діє:</span> {{ period }}</div>
      <div v-if="offer.contacts" class="detail__row"><span class="detail__label">Контакти:</span> {{ offer.contacts }}</div>
    </article>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.back { display: inline-block; margin-bottom: 12px; }
.detail__media { position: relative; border-radius: @radius; overflow: hidden; margin-bottom: 12px; }
.detail__media img { width: 100%; max-height: 360px; object-fit: cover; display: block; }
.detail__badge { position: absolute; top: 12px; left: 12px; }
.detail__provider { color: @muted; margin-bottom: 12px; }
.detail__desc { line-height: 1.5; }
.detail__row { margin: 6px 0; }
.detail__label { color: @muted; margin-right: 6px; }
.tag { display: inline-block; font-size: 13px; background: #eef2f7; color: @muted; border-radius: 6px; padding: 1px 8px; margin-right: 4px; }
.state { text-align: center; padding: 48px 0; color: @muted; }
</style>
