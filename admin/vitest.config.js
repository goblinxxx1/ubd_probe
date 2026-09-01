import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.js"],
    // Component tests mount the full ElementPlus library; under the parallel-worker
    // load of the whole suite the heavier ones (OfferForm*) exceed the 5s default and
    // flake. 15s is realistic headroom, still short enough to catch a genuinely hung test.
    testTimeout: 15000,
  },
});
