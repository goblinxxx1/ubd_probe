import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles/base.less";

createApp(App).use(router).mount("#app");
