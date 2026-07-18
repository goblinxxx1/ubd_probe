<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { extractError } from "@/utils/errors";

const auth = useAuthStore();
const router = useRouter();
const form = reactive({ email: "", password: "" });
const loading = ref(false);

async function submit() {
  loading.value = true;
  try {
    await auth.login(form.email, form.password);
    router.push({ name: "offers" });
  } catch (e) {
    ElMessage.error(extractError(e));
  } finally {
    loading.value = false;
  }
}

defineExpose({ submit, form });
</script>

<template>
  <div class="login">
    <el-form class="login-form" label-position="top" @submit.prevent="submit">
      <h2>UBD — Вхід</h2>
      <el-form-item label="Email">
        <el-input v-model="form.email" type="email" autocomplete="username" />
      </el-form-item>
      <el-form-item label="Пароль">
        <el-input v-model="form.password" type="password" autocomplete="current-password" />
      </el-form-item>
      <el-button type="primary" :loading="loading" native-type="submit">Увійти</el-button>
    </el-form>
  </div>
</template>

<style scoped lang="less">
@import "@/styles/variables.less";
.login { display: flex; justify-content: center; align-items: center; height: 100%; background: @bg; }
.login-form { width: 320px; padding: 28px 24px; background: @cream; border: 1px solid @divider; border-radius: 12px; }
.login-form h2 { margin: 0 0 18px; color: @text; }
.login-form .el-button { width: 100%; }
</style>
