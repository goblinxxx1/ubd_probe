<script setup>
import { computed, ref } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";
import { discountText } from "@/utils/format";
import OfferBadge from "@/components/OfferBadge.vue";

const props = defineProps({ offer: { type: Object, required: true } });
const image = computed(() => props.offer.image_url || placeholderDataUri(props.offer));
const discounts = computed(() => props.offer.discounts || []);
const showList = computed(() => discounts.value.length > 1);
const sourceLinks = computed(() =>
  props.offer.links?.length
    ? props.offer.links
    : (props.offer.site_url || props.offer.article_url
        ? [{ site_url: props.offer.site_url, article_url: props.offer.article_url }]
        : [])
);
const meta = computed(() => (props.offer.locations || []).join(" · "));
const logoBroken = ref(false);   // hide the badge gracefully if the remote logo 404s
</script>

<template>
  <div class="card">
    <div class="card__top">
      <div class="card__ident">
        <img v-if="offer.logo_url && !logoBroken" class="card__logo" :src="offer.logo_url"
             :alt="offer.provider" loading="lazy" @error="logoBroken = true" />
        <router-link class="card__provider" :to="{ name: 'offer', params: { id: offer.id } }">{{ offer.provider }}</router-link>
      </div>
      <img class="card__photo" :src="image" :alt="offer.provider" />
    </div>

    <div class="card__discount">
      <OfferBadge :offer="offer" />
      <span v-if="offer.title" class="card__dtext">{{ offer.title }}</span>
    </div>

    <ul v-if="showList" class="card__discounts">
      <li v-for="(d, i) in discounts" :key="i" class="card__discount-row">
        <span class="card__discount-val">{{ discountText(d) }}</span>
        <span v-if="d.label" class="card__discount-label">{{ d.label }}</span>
      </li>
    </ul>

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

    <div v-if="offer.offer_categories?.length" class="card__whom">
      <div class="card__whom-label">Тематика</div>
      <div class="card__chips">
        <span v-for="c in offer.offer_categories" :key="c.id" class="chip">{{ c.name }}</span>
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
.card__ident { display: flex; align-items: center; gap: 9px; min-width: 0; }
.card__logo {
  width: 30px; height: 30px; flex: none; object-fit: contain; border-radius: 7px;
  background: #fff; padding: 2px;   /* light chip so transparent/dark SVG logos stay legible in any theme */
}
.card__provider {
  font-weight: 900; font-size: 24px; line-height: .95; letter-spacing: -.3px; color: @text;
  overflow-wrap: anywhere; min-width: 0;
}
.card__provider:hover { text-decoration: none; color: @link; }
.card__photo {
  width: 60px; height: 60px; flex: none; object-fit: contain; border-radius: 9px;
}
.card__discount { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.card__dtext { font-size: 16px; }
.card__discounts { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.card__discount-row { display: flex; align-items: baseline; gap: 8px; font-size: 14px; }
.card__discount-val { font-weight: 800; color: @text; white-space: nowrap; }
.card__discount-label { color: @desc-muted; overflow-wrap: anywhere; }
.card__desc { font-size: 12px; line-height: 1.5; color: @desc-muted; margin: 10px 0 0; overflow-wrap: anywhere; }
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
  font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
  background: @chip-bg; color: @chip-text;
}
.card__foot {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  flex-wrap: wrap; margin-top: 12px; padding-top: 10px; border-top: 1px solid @card-border;
}
.card__meta { font-size: 14px; letter-spacing: .2px; color: @meta-muted; }
.card__links { display: flex; gap: 8px; flex-wrap: wrap; }
.card__link {
  font-size: 14px; font-weight: 700; color: @link; line-height: 1;
  padding: 7px 12px; border-radius: 8px; border: 1px solid @card-border;
}
.card__link:hover { background: @whom-bg; text-decoration: none; }
</style>
