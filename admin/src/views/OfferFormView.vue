<script setup>
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import * as offers from "@/api/offers";
import { useDictionariesStore } from "@/stores/dictionaries";
import { extractError } from "@/utils/errors";
import OfferForm from "@/components/OfferForm.vue";

const route = useRoute();
const router = useRouter();
const dictionaries = useDictionariesStore();

const id = route.params.id || null;
const initial = ref(null);

onMounted(async () => {
  await dictionaries.load();
  if (id) {
    try {
      initial.value = await offers.get(id);
    } catch (e) {
      ElMessage.error(extractError(e));
    }
  }
});

async function onSubmit(payload) {
  try {
    if (id) {
      await offers.update(id, payload);
      ElMessage.success("Збережено");
    } else {
      await offers.create(payload);
      ElMessage.success("Створено");
    }
    router.push({ name: "offers" });
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ onSubmit });
</script>

<template>
  <div class="offer-form-view">
    <h2>{{ id ? "Редагувати оффер" : "Створити оффер" }}</h2>
    <OfferForm
      :initial="initial"
      :target-categories="dictionaries.targetCategories"
      :offer-categories="dictionaries.offerCategories"
      @submit="onSubmit"
      @cancel="router.push({ name: 'offers' })"
    />
  </div>
</template>
