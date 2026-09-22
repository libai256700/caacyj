import { createSSRApp } from "vue";
import App from "./App.vue";
import uvUI from "@climblee/uv-ui";
import { createAppSafeAreaStyle } from "@/utils/appSafeArea";

export function createApp() {
  const app = createSSRApp(App);
  app.use(uvUI);
  app.config.globalProperties.$appSafeAreaStyle = createAppSafeAreaStyle();

  return {
    app,
  };
}
