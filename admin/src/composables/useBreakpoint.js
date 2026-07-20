import { ref, onMounted, onUnmounted } from "vue";

export function useBreakpoint() {
  const mqMobile = window.matchMedia("(max-width: 640px)");
  const mqTablet = window.matchMedia("(max-width: 1024px)");
  const isMobile = ref(mqMobile.matches);
  const isTablet = ref(mqTablet.matches);

  const update = () => {
    isMobile.value = mqMobile.matches;
    isTablet.value = mqTablet.matches;
  };

  onMounted(() => {
    mqMobile.addEventListener("change", update);
    mqTablet.addEventListener("change", update);
  });
  onUnmounted(() => {
    mqMobile.removeEventListener("change", update);
    mqTablet.removeEventListener("change", update);
  });

  return { isMobile, isTablet };
}
