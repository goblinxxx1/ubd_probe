export function extractError(err) {
  const detail = err?.response?.data?.detail;
  if (detail) return detail;
  if (err?.message) return err.message;
  return "Сталася помилка";
}
