<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <el-select
    :model-value="modelValue"
    multiple
    style="width: 100%"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-option v-for="o in options" :key="o.id" :label="o.name" :value="o.id" />
  </el-select>
</template>
