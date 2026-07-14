export function placeholderText({ type, discount_type }) {
  if (type === "event" || discount_type === "free") return "безкоштовно для УБД";
  return "знижка для УБД";
}

export function placeholderDataUri(offer) {
  const text = placeholderText(offer);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="225">` +
    `<rect width="100%" height="100%" fill="#4B5320"/>` +
    `<text x="50%" y="50%" fill="#ffffff" font-family="sans-serif" font-size="24" ` +
    `text-anchor="middle" dominant-baseline="middle">${text}</text>` +
    `</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
