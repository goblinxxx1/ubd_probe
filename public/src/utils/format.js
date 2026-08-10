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
  return `${dd}.${mm}.${d.getUTCFullYear()}`;
}

export function discountText(d) {
  if (d.discount_type === "free") return "Безкоштовно";
  if (d.discount_type === "percent" && d.discount_value != null) return `−${Number(d.discount_value)}%`;
  if (d.discount_type === "fixed" && d.discount_value != null) return `−${Number(d.discount_value)} ₴`;
  if (d.discount_type === "special_price" && d.discount_value != null) return `Ціна ${Number(d.discount_value)} ₴`;
  return "Знижка";
}

export function offerBadge(offer) {
  if (offer.type === "event") return { text: "Подія", kind: "event" };
  if (offer.discount_type === "free") return { text: "Безкоштовно", kind: "free" };
  if (offer.discount_type === "percent" && offer.discount_value != null) {
    return { text: `−${Number(offer.discount_value)}%`, kind: "discount" };
  }
  if (offer.discount_type === "fixed" && offer.discount_value != null) {
    return { text: `−${Number(offer.discount_value)} ₴`, kind: "discount" };
  }
  if (offer.discount_type === "special_price") {
    return { text: "Спеціальна ціна", kind: "discount" };
  }
  return { text: "Знижка", kind: "discount" };
}
