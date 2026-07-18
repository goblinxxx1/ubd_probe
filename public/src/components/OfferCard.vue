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
const meta = computed(() =>
  [props.offer.offer_categories?.[0]?.name, props.offer.location].filter(Boolean).join(" · ")
);
</script>

<template>
  <div class="card">
    <div class="card__top">
      <router-link class="card__provider" :to="{ name: 'offer', params: { id: offer.id } }">{{ offer.provider }}</router-link>
      <img class="card__photo" :src="image" :alt="offer.provider" />
    </div>

    <div class="card__discount">
      <OfferBadge :offer="offer" />
      <span v-if="offer.title" class="card__dtext">{{ offer.title }}</span>
    </div>

    <p class="card__desc">
      <template v-if="offer.description">{{ offer.description }}</template>
      <span v-else class="card__desc-empty">[опис]</span>
    </p>

    <div v-if="offer.target_categories?.length" class="card__whom">
      <div class="card__whom-label">Для кого</div>
      <div class="card__chips">
        <span v-for="t in offer.target_categories" :key="t.id" class="chip">{{ t.name }}</span>
      </div>
    </div>

    <div v-if="meta || sourceLinks.length" class="card__foot">
      <span v-if="meta" class="card__meta">{{ meta }}</span>
      <span v-if="sourceLinks.length" class="card__links">
        <template v-for="(l, i) in sourceLinks" :key="i">
          <a v-if="l.site_url" class="card__link" :href="l.site_url"
             target="_blank" rel="noopener">Сайт{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
          <a v-if="l.article_url" class="card__link" :href="l.article_url"
             target="_blank" rel="noopener">Новина{{ sourceLinks.length > 1 ? ' ' + (i + 1) : '' }}</a>
        </template>
      </span>
    </div>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.card {
  display: flex; flex-direction: column;
  background: @card-bg; border: 2px solid @card-border; border-radius: @radius;
  padding: 14px; color: @text;
}
.card__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card__provider {
  font-weight: 900; font-size: 24px; line-height: .95; letter-spacing: -.3px; color: @text;
}
.card__provider:hover { text-decoration: none; color: @link; }
.card__photo {
  width: 26px; height: 26px; flex: none; object-fit: cover; border-radius: 9px;
}
.card__discount { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.card__dtext { font-size: 12px; }
.card__desc { font-size: 11.5px; line-height: 1.45; color: @desc-muted; margin: 10px 0 0; }
.card__desc-empty { color: @placeholder; font-style: italic; }
.card__whom {
  background: @whom-bg; border: 1px solid @whom-border; border-radius: 8px; padding: 7px 9px; margin-top: 11px;
}
.card__whom-label {
  font-size: 8px; text-transform: uppercase; letter-spacing: 1.5px; color: @meta-muted;
  font-weight: 700; margin-bottom: 5px;
}
.card__chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
  background: @chip-bg; color: @chip-text;
}
.card__foot {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  margin-top: 12px; padding-top: 10px; border-top: 1px solid @card-border;
}
.card__meta { font-size: 9.5px; text-transform: uppercase; letter-spacing: 1px; color: @meta-muted; }
.card__links { display: flex; gap: 10px; flex-wrap: wrap; }
.card__link { font-size: 11px; font-weight: 700; color: @link; }
</style>
