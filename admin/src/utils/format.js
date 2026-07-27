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
