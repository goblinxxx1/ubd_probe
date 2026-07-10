export function enumLabel(list, value) {
  const found = list.find((item) => item.value === value);
  return found ? found.label : value;
}

export function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const yyyy = d.getUTCFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

const STATUS_TAG = {
  pending_review: "warning",
  published: "success",
  rejected: "danger",
  expired: "info",
};

export function statusTagType(status) {
  return STATUS_TAG[status] || "info";
}
