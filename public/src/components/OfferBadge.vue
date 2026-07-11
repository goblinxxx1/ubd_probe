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
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 13px; font-weight: 600; color: #fff; }
.badge--event { background: #6d28d9; }
.badge--free { background: #059669; }
.badge--discount { background: @brand; }
</style>
