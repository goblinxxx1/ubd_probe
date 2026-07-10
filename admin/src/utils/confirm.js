import { ElMessageBox } from "element-plus";

export function confirmDelete(message = "Видалити цей запис?") {
  return ElMessageBox.confirm(message, "Підтвердження", {
    type: "warning",
    confirmButtonText: "Так",
    cancelButtonText: "Скасувати",
  });
}
