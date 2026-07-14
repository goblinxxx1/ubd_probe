export function validateOffer(form) {
  const errors = [];
  if (!form.title) errors.push("Вкажіть заголовок");
  if (!form.provider) errors.push("Вкажіть провайдера");
  if (form.valid_from && form.valid_until && form.valid_until < form.valid_from) {
    errors.push("Дата «до» раніше за дату «від»");
  }
  const needsValue =
    form.type === "discount" && (form.discount_type === "percent" || form.discount_type === "fixed");
  const hasValue = form.discount_value !== null && form.discount_value !== "" && form.discount_value !== undefined;
  if (needsValue && !hasValue) errors.push("Вкажіть величину знижки");
  if (!needsValue && hasValue) errors.push("Величина знижки лише для відсоток/фіксована");
  const urlBad = (v) => v && !/^https?:\/\//.test(v);
  if (urlBad(form.site_url)) errors.push("«Сайт» має починатися з http:// або https://");
  if (urlBad(form.article_url)) errors.push("«Сторінка новини» має починатися з http:// або https://");
  return errors;
}

export function buildOfferPayload(form) {
  const isDiscount = form.type === "discount";
  const withValue = isDiscount && (form.discount_type === "percent" || form.discount_type === "fixed");
  return {
    type: form.type,
    title: form.title,
    description: form.description || "",
    provider: form.provider,
    location: form.location || null,
    valid_from: form.valid_from || null,
    valid_until: form.valid_until || null,
    discount_type: isDiscount ? form.discount_type || null : null,
    discount_value: withValue ? form.discount_value : null,
    site_url: form.site_url || null,
    article_url: form.article_url || null,
    image_url: form.image_url || null,
    target_category_ids: form.target_category_ids || [],
    offer_category_ids: form.offer_category_ids || [],
  };
}
