# UBD — як продовжувати роботу (по одному треку на сесію)

Кожен трек робимо в **окремій новій сесії Claude Code**, щоб не тягнути зайвий контекст.
Уся потрібна пам'ять автозавантажується з `~/.claude/projects/D--ubd-probe/memory/`
(файл `MEMORY.md` + пов'язані), тож нова сесія одразу знає стан проєкту.

## Стан проєкту (станом на 2026-07-20) — усе в `main` і на GitHub

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
12. **UI-редизайн public+admin** — світлий бурштиновий стиль, шрифт UAF Memory, картка
    оффера з блоком «Для кого», Element Plus theme override у адмінці, клікабельні
    посилання; + косметика.
13. **Ревізія обох фронтів** — WCAG AA контраст (затемнені muted-токени, амбер-як-текст
    → `@link`), видимі `:focus-visible`, теракота-помилка, рестайл public-хвостів
    (Pagination/OfferGrid-стани/h1), a11y (`alt`, `aria-*`). Аудит із контраст-математикою:
    `docs/superpowers/specs/2026-07-18-both-fronts-revision-audit.md`.
14. **Crawler active-harvest (варіант A)** — активний пошук → оффер прямо в модерацію; джерело лише як побічний продукт атрибуції. [[ubd-crawler-discovery-redesign]].
15. **Crawler точність атрибуції + місто + дубль картки** — blocklist медіа/держ/сток/агрегаторів, rule N≤1, газетир міст, «Онлайн». [[ubd-crawler-discovery-redesign]].
16. **Crawler авто-тематика** — курований лексикон + auto-create offer-категорій через internal-ендпоінт `POST /api/internal/offer-categories` (X-API-Key); прибрано yandex з ddgs. [[ubd-crawler-auto-category]].
17. **Мобільний фікс фільтрів** public (панель → повноекранна модалка).
18. **Адаптивна верстка admin+public** — `ResponsiveTable` (el-table↔картки), off-canvas drawer ≤1024, `useBreakpoint`; public overflow-wrap/audit; + усі 5 follow-ups рев'ю. [[ubd-ui-responsive]].
19. **Self-growing discovery** — 3 треки: query-grid ([[ubd-crawler-query-grid]]), brand→domain feed ([[ubd-crawler-brand-domain-feed]]), **sitemap-глибина** ([[ubd-crawler-sitemap-depth]]): DomainWalker розкриває website-кандидата homepage→промо-сторінки (robots→sitemap→BFS≤2) з per-domain політ-шаром; crawler 269/269. Зв'язка brand-feed→глибина→модерація виробляє офери.

**Свідомо НЕ роблено:** C2 (сегментація тексту в блоці) — реальні дані показали непотрібність; деталі у пам'яті [[ubd-discovery-plan]].

## ⚠️ Відкриті пункти (для наступних сесій)

- **Пошук деградований:** активне відкриття глушать rate-limit/CAPTCHA пошуковиків; **Brave API відкинуто користувачем**; SearXNG зараз віддає **0** результатів (усі апстріми блокуються) — досі в коді, але мертвий. Рекомендований reframe (**курований seed-каталог + пасивний кроул** замість відкритого пошуку) НЕ збудовано — гарний кандидат на наступний трік.
- **Атрибуція:** новинні/держ/агрегатор-сайти досі просочуються як фейкові провайдери (дають «шумні» багатокатегорійні офери). Посилення — відкладено.
- **Відкладене:** target-вісь лишається курованою; IG/FB-харвест; новинні Telegram-канали.
- **Дані:** у compose-БД `ubd` **0 оферів** (видалено на запит 2026-07-20). Сайт порожній.
- **Docker:** образи compose `admin`/`public` **застарілі** (не перезбирані після responsive-треку) — живий `:8080`/`:8082` НЕ показує адаптив. Для перевірки: `docker compose build admin public && docker compose up -d`.

**Наступний трек (рекомендація):** усі 3 P1-важелі self-growing discovery зроблено (query-grid +
brand-feed + sitemap-глибина) — DDG-незалежне джерело доменів + розкриття глибини вже виробляють
офери. Далі: **маркетинг-лексикон** (розширити промо/relevance-лексикон) або **domain-rating/snowball**
(самонаповнення списку доменів). Деталі й порядок — [[ubd-crawler-discovery-scaling-brainstorm]].
Альтернативи: посилення атрибуції проти медіа-провайдерів; IG/FB-харвест. Обовʼязкових немає.

**Як запускати:** повний довідник — `RUN.md` (окремо/разом, краулер, пошукові движки,
потік у адмінку); Docker-деталі — `README-docker.md`.

**Тести (перевірено 2026-07-20):** admin **84**, public **60**, crawler **139**, backend **63** —
усі зелені. Фронти перед мержем — ще й `npm run build` (Vitest НЕ компілює scoped-Less, тож
undefined-токен у `<style>` проходить тести, але валить build). Backend-тести потребують
`mysql-container` на :3306 (`docker start mysql-container`).

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
