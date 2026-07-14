<script setup>
import { reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { OFFER_TYPES, DISCOUNT_TYPES } from "@/constants/enums";
import { validateOffer, buildOfferPayload } from "@/utils/offerForm";
import ImagePreview from "@/components/ImagePreview.vue";
import CategoryMultiSelect from "@/components/CategoryMultiSelect.vue";

const props = defineProps({
  initial: { type: Object, default: null },
  targetCategories: { type: Array, default: () => [] },
  offerCategories: { type: Array, default: () => [] },
});
const emit = defineEmits(["submit", "cancel"]);

function fromInitial(o) {
  return {
    type: o?.type || "discount",
    title: o?.title || "",
    description: o?.description || "",
    provider: o?.provider || "",
    location: o?.location || "",
    valid_from: o?.valid_from || null,
    valid_until: o?.valid_until || null,
    discount_type: o?.discount_type || null,
    discount_value: o?.discount_value ?? null,
    site_url: o?.site_url || "",
    article_url: o?.article_url || "",
    image_url: o?.image_url || "",
    target_category_ids: o?.target_categories ? o.target_categories.map((c) => c.id) : [],
    offer_category_ids: o?.offer_categories ? o.offer_categories.map((c) => c.id) : [],
  };
}

const form = reactive(fromInitial(props.initial));
watch(() => props.initial, (o) => Object.assign(form, fromInitial(o)));

const isDiscount = computed(() => form.type === "discount");
const showValue = computed(
  () => isDiscount.value && (form.discount_type === "percent" || form.discount_type === "fixed")
);

watch(
  () => [form.type, form.discount_type],
  () => {
    if (!showValue.value) form.discount_value = null;
  }
);

function submit() {
  const errors = validateOffer(form);
  if (errors.length) {
    ElMessage.error(errors[0]);
    return;
  }
  emit("submit", buildOfferPayload(form));
}

defineExpose({ form, submit });
</script>

<template>
  <el-form label-position="top" class="offer-form">
    <el-form-item label="Тип" required>
      <el-select v-model="form.type" style="width: 200px">
        <el-option v-for="t in OFFER_TYPES" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="Заголовок" required>
      <el-input v-model="form.title" />
    </el-form-item>
    <el-form-item label="Опис">
      <el-input v-model="form.description" type="textarea" :rows="3" />
    </el-form-item>
    <el-form-item label="Хто пропонує (провайдер)" required>
      <el-input v-model="form.provider" />
    </el-form-item>
    <el-form-item label="Для кого">
      <CategoryMultiSelect v-model="form.target_category_ids" :options="targetCategories" />
    </el-form-item>
    <el-form-item label="Тематика">
      <CategoryMultiSelect v-model="form.offer_category_ids" :options="offerCategories" />
    </el-form-item>
    <el-form-item label="Локація">
      <el-input v-model="form.location" placeholder="Місто або «онлайн»" />
    </el-form-item>
    <el-form-item label="Дійсний від">
      <el-date-picker v-model="form.valid_from" type="date" value-format="YYYY-MM-DD" />
    </el-form-item>
    <el-form-item label="Дійсний до">
      <el-date-picker v-model="form.valid_until" type="date" value-format="YYYY-MM-DD" />
    </el-form-item>
    <template v-if="isDiscount">
      <el-form-item label="Тип знижки">
        <el-select v-model="form.discount_type" clearable style="width: 200px">
          <el-option v-for="d in DISCOUNT_TYPES" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="showValue" label="Величина знижки">
        <el-input-number v-model="form.discount_value" :min="0" />
      </el-form-item>
    </template>
    <el-form-item label="Сайт">
      <el-input v-model="form.site_url" placeholder="https://…" />
    </el-form-item>
    <el-form-item label="Сторінка новини">
      <el-input v-model="form.article_url" placeholder="https://…" />
    </el-form-item>
    <el-form-item label="Зображення (URL)">
      <el-input v-model="form.image_url" placeholder="https://…" />
    </el-form-item>
    <el-form-item label="Прев'ю">
      <ImagePreview :image-url="form.image_url" :type="form.type" :discount-type="form.discount_type" />
    </el-form-item>
    <div class="actions">
      <el-button type="primary" @click="submit">Зберегти</el-button>
      <el-button @click="emit('cancel')">Скасувати</el-button>
    </div>
  </el-form>
</template>

<style scoped lang="less">
.offer-form { max-width: 640px; }
.actions { display: flex; gap: 8px; }
</style>
