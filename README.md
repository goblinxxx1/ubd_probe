# UBD — платформа знижок для УБД

Платформа, що збирає й показує знижки та пільги для учасників бойових дій (УБД),
ветеранів, їхніх родин, працівників ДСНС/поліції тощо. Знахідки модеруються в
адмінці й публікуються на публічному сайті.

## Складові

| Сервіс | Стек | Роль |
|---|---|---|
| `backend/` | FastAPI · SQLAlchemy · MySQL | API (`/api`), модель даних, авторизація, модерація |
| `public/`  | Vue 3 · Vite · Less | Публічний сайт: опубліковані оффери, фільтри, деталі |
| `admin/`   | Vue 3 · Vite · Element Plus | Адмінка: модерація оферів і джерел, категорії, адміни |
| `crawler/` | Python | Обхід джерел (website/telegram/instagram/facebook) + активний пошук; шле знахідки в backend |

Потік даних: **crawler** знаходить джерела (пошук) і витягає оффери (обхід) →
пише в **backend** через внутрішній API → знахідки чекають у чергах **admin**
(«Запропоновані джерела» / «Черга модерації») → після схвалення оффери йдуть на **public**.

## Швидкий старт

```bash
cp .env.example .env
docker compose up -d --build
```

- Public: http://localhost:8080 · Admin: http://localhost:8082 (`admin@example.com` / `admin12345`) · API: http://localhost:8000/api/health

Повний довідник запуску (окремо/разом, краулер, пошукові движки, потік у адмінку) —
**[RUN.md](RUN.md)**. Деталі Docker-стеку — **[README-docker.md](README-docker.md)**.

## Стан

Усі складові завершені й у `main` (синхронізовано з `origin`): backend, public,
admin, crawler (+ active discovery: DuckDuckGo та SearXNG, дедуп, type-класифікація),
Docker-інфра, і UI-редизайн обох фронтів (світлий бурштиновий стиль, UAF Memory,
WCAG AA контраст, focus-стани, a11y). Спеки/плани по треках — у `docs/superpowers/`.

## Розробка

- Гілки: кожен трек — `feat/<track>` від `main`, merge (ff) назад.
- Спілкування в задачах — українською.
- Тести: `admin`/`public` — `npm test` (Vitest, backend не потрібен); `backend`/`crawler`
  — `pytest` з venv (backend потребує MySQL). Фронти перед мержем — ще й `npm run build`
  (Vitest не компілює scoped-Less).
