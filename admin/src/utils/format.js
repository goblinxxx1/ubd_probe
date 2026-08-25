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

export function isHttpUrl(v) {
  return typeof v === "string" && /^https?:\/\//i.test(v);
}

// Split a free-text note into ordered segments so embedded http(s) URLs can be
// rendered as links: [{ text }] for plain runs, [{ url }] for URLs.
export function noteSegments(note) {
  const text = typeof note === "string" ? note : "";
  if (!text) return [];
  const parts = [];
  const re = /(https?:\/\/[^\s]+)/gi;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ url: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

export function discountLabel(type, value) {
  if (type === "free") return "безкоштовно";
  const n = value == null ? null : Number(value);
  if (n == null || Number.isNaN(n)) return "";
  if (type === "percent") return `−${n}%`;
  if (type === "fixed") return `−${n} грн`;
  if (type === "special_price") return `${n} грн`;   // final price, not a discount off
  return "";
}

// One-glance discount summary for the queue row: single-discount label, or a count
// when an offer carries several, or "—" when it has none.
export function discountSummary(offer) {
  if (!offer) return "—";
  if (Array.isArray(offer.discounts) && offer.discounts.length > 1) {
    return `${offer.discounts.length} знижок`;
  }
  const label = discountLabel(offer.discount_type, offer.discount_value);
  return label || "—";
}

export function supersedeSummary(offer) {
  const p = offer && offer.supersedes;
  if (!p) return "";
  const was = discountLabel(p.discount_type, p.discount_value);
  const now = discountLabel(offer.discount_type, offer.discount_value);
  return `замінює #${p.id} (${was} → ${now})`;
}
