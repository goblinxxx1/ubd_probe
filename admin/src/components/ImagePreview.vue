<script setup>
import { computed } from "vue";
import { placeholderDataUri } from "@/utils/placeholder";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  type: { type: String, default: "discount" },
  discountType: { type: String, default: null },
});

const src = computed(
  () => props.imageUrl || placeholderDataUri({ type: props.type, discount_type: props.discountType })
);
</script>

<template>
  <img :src="src" alt="" class="image-preview" />
</template>

<style scoped lang="less">
.image-preview { max-width: 400px; max-height: 225px; border: 1px solid #eee; }
</style>
