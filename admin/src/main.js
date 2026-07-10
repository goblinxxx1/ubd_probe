import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import { setUnauthorizedHandler } from "./api/client";
import "./styles/global.less";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
app.use(ElementPlus);
app.use(router);

const auth = useAuthStore(pinia);
setUnauthorizedHandler(() => {
  auth.logout();
  router.push({ name: "login" });
});

app.mount("#app");
