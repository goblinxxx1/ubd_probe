import { defineStore } from "pinia";
import { ref } from "vue";
import * as offers from "@/api/offers";

// Shared pending-review count for the sidebar badge. Kept in a store so any view
// that mutates offers (publish/reject/delete/restore) can refresh it live.
export const useModerationStore = defineStore("moderation", () => {
  const pendingCount = ref(0);

  async function refresh() {
    try {
      const result = await offers.list({ status: "pending_review", size: 1 });
      pendingCount.value = result?.total ?? 0;
    } catch {
      // badge is non-critical — keep the previous value
    }
  }

  return { pendingCount, refresh };
});
