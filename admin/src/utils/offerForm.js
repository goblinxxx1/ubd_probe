// Discount types that carry a numeric value (percent/fixed = discount, special_price = final price).
export const VALUE_DISCOUNT_TYPES = ["percent", "fixed", "special_price"];

export function validateOffer(form) {
  const errors = [];
  if (!form.title) errors.push("Вкажіть заголовок");
  if (!form.provider) errors.push("Вкажіть провайдера");
  if (form.valid_from && form.valid_until && form.valid_until < form.valid_from) {
    errors.push("Дата «до» раніше за дату «від»");
  }
  const needsValue =
    form.type === "discount" && VALUE_DISCOUNT_TYPES.includes(form.discount_type);
  const hasValue = form.discount_value !== null && form.discount_value !== "" && form.discount_value !== undefined;
  if (needsValue && !hasValue) errors.push("Вкажіть величину знижки / ціну");
  if (!needsValue && hasValue) errors.push("Величина лише для відсоток/фіксована/спеціальна ціна");
  const urlBad = (v) => v && !/^https?:\/\//.test(v);
  if (urlBad(form.site_url)) errors.push("«Сайт» має починатися з http:// або https://");
  if (urlBad(form.article_url)) errors.push("«Сторінка новини» має починатися з http:// або https://");
  for (const d of form.discounts || []) {
    const needsValue = VALUE_DISCOUNT_TYPES.includes(d.discount_type);
    if (needsValue && (d.discount_value === null || d.discount_value === undefined)) {
      errors.push("Величина обов'язкова для %/фіксованої/спеціальної ціни");
    }
    if (!needsValue && d.discount_value !== null && d.discount_value !== undefined) {
      errors.push("Величина має бути порожньою, крім %/фіксованої/спеціальної ціни");
    }
  }
  return errors;
}

export function buildOfferPayload(form) {
  const isDiscount = form.type === "discount";
  const withValue = isDiscount && VALUE_DISCOUNT_TYPES.includes(form.discount_type);
  return {
    type: form.type,
    title: form.title,
    description: form.description || "",
    provider: form.provider,
    locations: form.locations || [],
    valid_from: form.valid_from || null,
    valid_until: form.valid_until || null,
    discount_type: isDiscount ? form.discount_type || null : null,
    discount_value: withValue ? form.discount_value : null,
    site_url: form.site_url || null,
    article_url: form.article_url || null,
    image_url: form.image_url || null,
    target_category_ids: form.target_category_ids || [],
    offer_category_ids: form.offer_category_ids || [],
    discounts: (form.discounts || []).map((d) => ({
      label: d.label || null,
      discount_type: d.discount_type || null,
      discount_value: d.discount_value ?? null,
    })),
  };
}
