# UBD — як продовжувати роботу (по одному треку на сесію)

Кожен під-проєкт («трек») робимо в **окремій новій сесії Claude Code**, щоб не тягнути зайвий
контекст. Уся потрібна пам'ять автозавантажується з `~/.claude/projects/D--ubd-probe/memory/`
(файл `MEMORY.md` + пов'язані), тож нова сесія одразу знає стан проєкту.

## Порядок треків

1. Бекенд і модель даних — **ЗАВЕРШЕНО**, у `main`.
2. Адмінка (Vue 3 SPA) — **ЗАВЕРШЕНО**, у `main`.
3. Публічний фронтенд (Vue 3 SPA + Less) — **ЗАВЕРШЕНО**, у `main`.
4. **Crawler** (сервіс за кроном) — наступний.

## Як почати новий трек

1. Відкрий **нову сесію** Claude Code в теці `D:\ubd_probe` (гілка `main`, дерево чисте).
2. Встав відповідний стартовий промпт (нижче). Далі Claude сам: створить фіча-гілку від `main`,
   проведе брейнсторм → spec → план → реалізацію (subagent-driven), і в кінці спитає про merge.
3. Коли трек готовий і влитий у `main` — заверши сесію. Наступний трек — знову нова сесія.

### Стартовий промпт для треку 4 (crawler) — наступний

```
Продовжуємо проєкт UBD (тека D:\ubd_probe, гілка main). Починаємо під-проєкт 4 — crawler:
сервіс за кроном, що обходить джерела (website/facebook/telegram/instagram), знаходить оффери
та пропонує нові джерела, усе через internal API бекенда (X-API-Key). Створи фіча-гілку
feat/crawler від main і почни з брейнсторму.
```

## Домовленості про гілки

- Кожен трек — своя гілка `feat/<track>` **від `main`**.
- Коли трек завершено і пройшов рев'ю — merge (fast-forward) у `main`, гілку видалити.
- Так кожна нова сесія стартує з повного, чистого `main`.

## Середовище (коротко; деталі — у пам'яті `ubd-dev-environment`)

- **Backend:** Python лише через venv — з `backend/`: `./.venv/Scripts/python.exe -m pytest -q`.
  Запуск API для ручної перевірки: `./.venv/Scripts/python.exe -m uvicorn app.main:app` (порт 8000).
- **Frontend (admin, і майбутній public):** Node/npm у PATH. `cd <app> && npm run dev` (Vite),
  `npm run test` (Vitest, API замоканий). Vite проксіює `/api` → `http://localhost:8000`.
- **MySQL:** Docker-контейнер `mysql-container` (root / my-secret-pw), схеми `ubd` і `ubd_test`.
  Якщо бекенд-тести не конектяться — `docker start mysql-container` (контейнер уже раз зникав).
- **Креденшели:** `backend/.env` (gitignored).

## Спеки і плани

`docs/superpowers/specs/` і `docs/superpowers/plans/` — по одному spec+plan на трек.
