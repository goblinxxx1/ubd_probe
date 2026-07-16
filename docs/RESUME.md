# UBD — як продовжувати роботу (по одному треку на сесію)

Кожен трек робимо в **окремій новій сесії Claude Code**, щоб не тягнути зайвий контекст.
Уся потрібна пам'ять автозавантажується з `~/.claude/projects/D--ubd-probe/memory/`
(файл `MEMORY.md` + пов'язані), тож нова сесія одразу знає стан проєкту.

## Стан проєкту (станом на 2026-07-16) — усе в `main` і на GitHub

`main` синхронізовано з `origin` (`https://github.com/goblinxxx1/ubd_probe.git`), дерево чисте.

**Завершено й влито в `main`:**
1. Бекенд і модель даних (FastAPI/SQLAlchemy/MySQL).
2. Адмінка (Vue 3 SPA).
3. Публічний фронтенд (Vue 3 SPA + Less).
4. **Crawler** (website/telegram/instagram/facebook, internal API, пасивний discovery).
5. **Docker-інфра** застосунку (`docker compose up`: db+backend+public:8080+admin:8082; краулер за профілем `crawler`; `README-docker.md`).
6. **Трек 0** — presentation оффера: `site_url`/`article_url` посилання, лого сайту, заглушка `#4B5320`, шрифт **UAF Memory**.
7. **Discovery A** — DuckDuckGo (`ddgs`) active search → `suggested_sources`.
8. **Discovery B** — SearXNG (self-hosted сервіс під профілем crawler) як другий провайдер.
9. **Discovery C** — дедуп/merge офферів за `target_url` (нова таблиця `offer_links`, multi-link у public).
10. **Discovery D** — type-класифікація результатів пошуку (`t.me`→telegram тощо, відсів соц-junk).
11. **nginx resolver фікс** (502 після ребілду backend усунуто).

**Свідомо НЕ роблено:** C2 (сегментація тексту в блоці) — реальні дані показали непотрібність; деталі у пам'яті [[ubd-discovery-plan]].

**Наступний трек (узгоджено, ще НЕ реалізовано):** UI-редизайн public+admin. Дизайн-напрям обрано на брейнстормі (світлий мінімалізм, бурштин-акцент, UAF Memory, картка з блоком «Для кого», місце під опис компанії) — усі деталі й відкриті правки у пам'яті [[ubd-ui-redesign]]; мокапи в `.superpowers/brainstorm/1991-1784226233/content/`.

**Тести:** backend 58, crawler 79, admin 72, public 47.

## Як почати новий трек

1. Нова сесія Claude Code в `D:\ubd_probe` (гілка `main`, дерево чисте).
2. Опиши задачу — Claude сам створить фіча-гілку `feat/<track>` від `main`,
   проведе брейнсторм → spec → план → реалізацію (TDD, часті коміти), і в кінці спитає про merge.
3. Коли трек влитий у `main` (+ push за бажанням) — заверши сесію.

## Домовленості

- Кожен трек — своя гілка `feat/<track>` **від `main`**; по завершенні — merge (ff) у `main`, гілку видалити.
- **Запуск застосунку — тільки в Docker** ([[ubd-run-in-docker]]), не хостовими процесами. Хостовий запуск — лише для тестів.
- Спілкування — **українською** ([[language-preference]]).
- Точка відновлення до цієї сесії — git-тег `checkpoint-2026-07-16-discovery-done`.

## Середовище (деталі — у пам'яті `ubd-dev-environment`)

- **Backend/crawler тести:** з `backend/` або `crawler/`: `./.venv/Scripts/python.exe -m pytest -q` (потрібен `mysql-container` для backend — `docker start mysql-container`, він періодично зникає).
- **Frontend тести:** `cd admin|public && npm test` (Vitest, API замоканий).
- **Docker-стек:** `cp .env.example .env && docker compose up -d --build`; краулер-демо — `README-docker.md`.
- **Вихідна адреса краулера для firewall:** `192.168.20.69` (LAN-IP хоста; деталі в `README-docker.md`).

## Спеки і плани

`docs/superpowers/specs/` і `docs/superpowers/plans/` — по одному spec+plan на трек.
