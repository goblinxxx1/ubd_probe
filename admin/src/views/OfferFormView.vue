<script setup>
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import * as offers from "@/api/offers";
import { useDictionariesStore } from "@/stores/dictionaries";
import { useModerationStore } from "@/stores/moderation";
import { extractError } from "@/utils/errors";
import OfferForm from "@/components/OfferForm.vue";

const route = useRoute();
const router = useRouter();
const dictionaries = useDictionariesStore();
const moderation = useModerationStore();

const id = route.params.id || null;
const initial = ref(null);

// Return to the section (and tab) the user came from, carried as query on entry;
// falls back to the offers list.
function backToOrigin() {
  const from = route.query.from || "offers";
  const query = route.query.tab ? { tab: route.query.tab } : {};
  router.push({ name: from, query });
}

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
    // An edit/create can change what sits in the pending queue (status change,
    // supersede) — keep the sidebar badge live without a reload.
    moderation.refresh();
    backToOrigin();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

async function onSubmitPublish(payload) {
  try {
    await offers.update(id, payload);
    await offers.publish(id);
    ElMessage.success("Збережено та опубліковано");
    moderation.refresh();   // offer just left the pending queue — refresh the badge
    backToOrigin();
  } catch (e) {
    ElMessage.error(extractError(e));
  }
}

defineExpose({ onSubmit, onSubmitPublish, backToOrigin });
</script>

<template>
  <div class="offer-form-view">
    <h2>{{ id ? "Редагувати оффер" : "Створити оффер" }}</h2>
    <OfferForm
      :initial="initial"
      :target-categories="dictionaries.targetCategories"
      :offer-categories="dictionaries.offerCategories"
      @submit="onSubmit"
      @submit-publish="onSubmitPublish"
      @cancel="backToOrigin"
    />
  </div>
</template>
