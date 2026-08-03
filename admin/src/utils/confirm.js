import { ElMessageBox } from "element-plus";

export function confirmDelete(message = "Видалити цей запис?") {
  return confirmAction(message);
}

export function confirmAction(message, title = "Підтвердження") {
  return ElMessageBox.confirm(message, title, {
    type: "warning",
    confirmButtonText: "Так",
    cancelButtonText: "Скасувати",
  });
}
