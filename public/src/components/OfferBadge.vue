<script setup>
import { computed } from "vue";
import { offerBadge } from "@/utils/format";

const props = defineProps({ offer: { type: Object, required: true } });
const badge = computed(() => offerBadge(props.offer));
</script>

<template>
  <span class="badge" :class="`badge--${badge.kind}`">{{ badge.text }}</span>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.badge {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 3px 9px; border-radius: 5px;
  font-size: 13px; font-weight: 800; line-height: 1; letter-spacing: -.2px;
}
.badge--discount { background: @badge-discount-bg; color: @badge-discount-text; }
.badge--free { background: @badge-free-bg; color: @badge-free-text; }
.badge--event { background: @badge-event-bg; color: @badge-event-text; }
</style>
