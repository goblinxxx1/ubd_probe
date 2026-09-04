# Crawler health monitor (admin panel) — design

Дата: 2026-09-04
Гілка: `feat/crawler-health-monitor`

## Мета

Зробити «що відбувається в краулері» повторювано видимим в адмінці — фундамент для рішень Фази 2. Живий зріз 2026-09-04 вручну показав кризу (3/4 бекенди в карантині, канал тримається на brave); цього не мало б доводитись діставати скриптом.

## Архітектура (лягає в наявний потік crawler → /api/internal → DB → /api/admin → Vue)

- Краулер у `run_loop` — новий best-effort тік `report_health_tick(config)` (поряд з learn/refresh/rejudge), раз на `health_report_interval_seconds` (дефолт 300с). Читає `SearchState.load(config.search_state_path)`, рахує зведення, постить.
- `api_client.report_crawler_health(payload)` → **новий** `POST /api/internal/crawler-health` (X-API-Key, `require_api_key`).
- Backend зберігає ОСТАННІЙ снапшот у singleton-таблиці `crawler_health` (`id=1`, `snapshot` JSON, `reported_at`). Upsert on POST. Alembic-міграція (down_revision `6da7b45bd2ea`).
- Адмінка: `GET /api/admin/crawler-health` (`get_current_admin`) → нова вкладка `CrawlerHealthView.vue` + nav-лінк.

Межі: краулер сам інтерпретує свій state; backend зберігає непрозорий JSON (не знає формату state-файлу); адмінка рендерить відомий шейп (еволюціонують разом).

## Снапшот (шейп, який рахує краулер)

```json
{
  "backends": [{"name","fails","cooldown_s","quarantine_s","status"}],   // status: healthy|cooling|quarantined
  "global_backoff_s": 0,
  "phrases": {"tracked": 1054, "productive": 766, "starved": 0},          // starved = tries>=3 & ewma~0
  "recall": {"grid_cursor": 2333, "cache_entries": 3626},
  "noise_hosts": [{"host","count"}],                                       // top-8 host_freq
  "generated_at": "<iso>"
}
```

`reported_at` (серверний час прийому) — окремо від `generated_at` (час на краулері), щоб адмінка показувала вік.

## Компоненти й тести (TDD)

**Backend**
- `models/crawler_health.py` — singleton (`id`, `snapshot` JSON, `reported_at`).
- alembic-міграція.
- schema `CrawlerHealthReport` (in) / `CrawlerHealthOut`.
- `POST /api/internal/crawler-health` (upsert). Тест: постить → рядок оновлюється; без ключа → 401/403.
- `GET /api/admin/crawler-health` (latest або 204/`null`). Тест: після POST повертає снапшот; без снапшоту → порожньо; без адмін-сесії → 401.

**Crawler**
- config: `health_report_interval_seconds: int = 300`.
- `api_client.report_crawler_health(payload)` — POST, best-effort. Тест: викликає правильний шлях/тіло.
- `runner.report_health_tick(config)` — рахує зведення зі `SearchState` і постить. Тести: коректний підрахунок (backends/phrases/starved/backoff зі змодельованого state); best-effort (виняток не кидає).
- `__main__` run_loop: врахувати `report=…, report_interval_seconds=…` (той самий патерн, що learn/refresh/rejudge). Тест на wiring — за наявним стилем scheduler.

**Admin**
- `api/crawlerHealth.js` — GET.
- `CrawlerHealthView.vue` — таблиця бекендів (колір за статусом), картки фраз/recall, список шум-хостів, вік снапшоту, кнопка «Оновити».
- router + nav-лінк «Здоров'я краулера».
- Тонкий Vitest-тест рендер/фетч за наявним патерном в'ю.

## Помилки/крайові

- Тік best-effort: падіння логується, не вбиває loop (як learn/refresh/rejudge).
- Немає снапшоту (свіжий деплой) → адмінка показує «Ще не зголошено».
- Снапшот застарів (краулер стоїть) → показуємо вік; порогів/алертів НЕ робимо (v1).

## Свідомо поза v1 (YAGNI)

- Історія в часі / графіки (лише останній снапшот).
- Алерти/пороги.
- Керування краулером з адмінки (лише перегляд).

Фаза 2 (ємність каналів — чи вертати google в пул за живою метрикою; per-engine health SearXNG; чистка engine-set) — ОКРЕМИЙ трек ПІСЛЯ; цей моніторинг буде її очима.
