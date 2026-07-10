export const OFFER_TYPES = [
  { value: "discount", label: "Знижка" },
  { value: "event", label: "Подія" },
];

export const DISCOUNT_TYPES = [
  { value: "percent", label: "Відсоток" },
  { value: "fixed", label: "Фіксована" },
  { value: "free", label: "Безкоштовно" },
];

export const OFFER_STATUSES = [
  { value: "pending_review", label: "На модерації" },
  { value: "published", label: "Опубліковано" },
  { value: "rejected", label: "Відхилено" },
  { value: "expired", label: "Прострочено" },
];

export const SOURCE_TYPES = [
  { value: "website", label: "Вебсайт" },
  { value: "facebook", label: "Facebook" },
  { value: "telegram", label: "Telegram" },
  { value: "instagram", label: "Instagram" },
];

export const ADMIN_ROLES = [
  { value: "super_admin", label: "Супер-адмін" },
  { value: "moderator", label: "Модератор" },
];

export const SUGGESTION_STATUSES = [
  { value: "pending", label: "Очікує" },
  { value: "approved", label: "Схвалено" },
  { value: "rejected", label: "Відхилено" },
];
