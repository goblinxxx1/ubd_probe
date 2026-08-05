# UBD — як продовжувати роботу (по одному треку на сесію)

Кожен трек робимо в **окремій новій сесії Claude Code**, щоб не тягнути зайвий контекст.
Уся потрібна пам'ять автозавантажується з `~/.claude/projects/D--ubd-probe/memory/`
(файл `MEMORY.md` + пов'язані), тож нова сесія одразу знає стан проєкту.

## Стан проєкту (станом на 2026-07-23) — усе в `main` і на GitHub

`main` синхронізовано з `origin` (`https://github.com/goblinxxx1/ubd_probe.git`), дерево чисте.

**Завершено й влито в `main`:**
1. Бекенд і модель даних (FastAPI/SQLAlchemy/MySQL).
2. Адмінка (Vue 3 SPA).
3. Публічний фронтенд (Vue 3 SPA + Less).
4. **Crawler** (website/telegram/instagram/facebook, internal API, пасивний discovery).
5. **Docker-інфра** застосунку (`docker compose up`: db+backend+public:8080+admin:8082; краулер за профілем `crawler`; `README-docker.md`).
6. **Трек 0** — presentation оффера: `site_url`/`article_url` посилання, лого сайту, заглушка `#4B5320`, шрифт **UAF Memory**.
7. **Discovery A** — DuckDuckGo (`ddgs`) active search → `suggested_sources`.
8. **Discovery B** — SearXNG (self-hosted сервіс) був другим провайдером. **РЕТАЙРНУТО 2026-08-05** (трек #33): наживо віддавав 0 придатних результатів — структурний блок (апстрім-рушії CAPTCHA-ять наш IP; Bing підсовує decoy-мотлох на комерційні кириличні запити). Активний пошук тепер — лише DuckDuckGo.
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
20. **Маркетинг-лексикон / автонаповнення** ([[ubd-crawler-marketing-lexicon-autofill]]) — самонавчальний промо-словник: єдиний `promo_lexicon` (SEED+LEARNED), детермінований labeler+корпус, офлайн log-odds майнер (pymorphy3), вето (multi-domain/PASS-collision/abstention), snowball з прийнятих оферів (backend `GET /api/internal/approved-offers`), людський audit-CLI (approve→LEARNED — єдиний шлях у живий гейт). Gated `autofill_enabled` (дефолт OFF). crawler 299/299, backend 84/84. Живий гейт лишається детермінованим; навчання офлайн.
21. **Domain-rating** (self-growing discovery lever 3, [[ubd-crawler-domain-rating]]) — самонаповнюваний рейтинг доменів: `DomainRegistry` (crawler-side JSON, exp-decay score) запамʼятовує productive website-домени, `DomainFeed` DDG-незалежно ре-фідить топ як кандидатів (список росте сам); активний harvester скіпає заапрувлені домени (host-skip, економія запитів) і записує рейтинг; пасивний source-loop **глибоко краулить усі сторінки** заапрувленого домену (`DomainWalker` посторінково) заради свіжих знижок. Gated `domain_rating_enabled` (дефолт ON), OFF byte-еквівалентно. crawler 324/324; opus-рев'ю READY 0C/0I.

22. **Посилення атрибуції** (self-growing медіа/агрегатор host-blocklist, [[ubd-crawler-attribution-hardening]]) — 3 шари: **A (живий гейт)** `RawItem.is_article`/`has_business_schema` зі schema.org; `attribute()` трактує article/агрегатор-сторінки як never-first-party зі salvage через outbound-лінк; `is_blocked_host` = статичний SEED + фетчнутий LEARNED; майстер-кноб `ATTRIBUTION_HARDENING_ENABLED` (OFF → byte-еквівалентний відкат живого гейту до pre-track). **B (офлайн)** корпус адитивно (`is_article`/`outbound_hosts`/`url`); `host_miner` per-host агрегація медіа/агрегатор-доказів проти provider-evidence; `host_vetoes` (support/provider/protected bare-host-нормалізовані/already-blocked); `run_host_miner` сабмітить кандидатів у backend-аудит-чергу. **C (backend+Vue)** таблиця `blocked_hosts` + crud + internal/admin ендпоінти + Vue-в'ю «Медіа-блоклист» (http-guarded sample-лінки). 14 TDD-тасок + opus whole-branch рев'ю + fix-хвиля (3 Important: kill-switch, protected scheme-mismatch, sample_urls=URL). crawler 350 / backend 92 / admin 89. Merge `6dd4e48`. Живий гейт детермінований, навчання офлайн, людське затвердження — єдиний шлях у живий блоклист.

23. **Cleanup-minors краулера** ([[ubd-crawler-cleanup-minors]]) — прибиральний трек, 6 tech-debt пунктів (A–F), crawler-only: (A) `AGGREGATOR_MIN_OUTBOUND` протягнуто у живий гейт (дефолт 3 byte-eq); (B) `_ARTICLE_TYPE` ловить `*Article`-підтипи + `Report`; (C) None-guard у host_miner; (D) консолідація ~10 копіпаст bare-host ідіом на спільний `util/hosts.py::bare_host` (D1 хелпер+тести, D2 міграція, контракти str|None/str через обгортки); (E) hoist import у test_blocklist; (F) tie-break тест `DomainRegistry.top()`. 7 TDD-тасок, фінальне opus рев'ю Ready-to-merge 0C/0I. crawler 361. Merge `3f95fa0`.

24. **Вузький per-domain `site:`** (self-growing discovery P3-recall, [[ubd-crawler-site-query]]) — gated левер: для productive (`DomainRegistry.top`) **та заапрувлених партнерів** видає вузькі `site:{домен} {intent-термін}` через наявний пошуковий шлях, щоб дістати промо-сторінки поза sitemap/BFS walker'а. `SiteQueryPlanner` (intent-only терміни, ротація term-фази), `SearchState.site_cursor` + незалежний `approved_cursor` (повний sweep великого набору партнерів), `SourceCandidate.bypass_host_skip` + гейт harvester (site:-сторінки заапрувлених доменів фетчаться, бо host-skip захищав лише дубль пасивного walk), union-пул у Runner (registry ⋈ ротовані approved через `zip_longest`). Прапори `site_query_enabled` (дефолт ON) / `site_query_budget` (5). Стріляє лише коли site_query_enabled **І** active_discovery **І** domain_rating_enabled; OFF байт-еквівалентно. Merge `fc693a0`. crawler 381 (361+20). Фінальне opus-рев'ю зловило Important (моя план-помилка: ротація партнерів була прив'язана до term-курсора → обрізала покриття >7 партнерів) — виправлено окремим `approved_cursor` + регресійний full-sweep тест; re-review чисто.

25. **Канонічний дедуп оферів** (backend, закриття гепу #2 аудиту цілісності, [[ubd-backend-dedup-canonical]]) — мердж оферів матчив по **сирому** `target_url`, тож дублі, що різнилися лише utm/click-id/`www.`/схемою, не зливались. Додано бекенд-обчислюваний ключ `Offer.target_url_canonical` (єдине джерело істини) + індекс + Alembic-міграція з backfill (без ретро-мерджу). `canonicalize_target_url` у `app/core/urlnorm.py` (drop www, http↔https-злиття, strip utm_*+курований click-id, sorted query). `create_offer` дедупить по canonical (+`order_by(id)` детермінізм), `update_offer` перераховує; merge-політика збережена (адмін дедуп не запускає; краулер→адмін мердж лишається). Сирий `target_url` лишається для кліку; API/схеми/public незмінні. Merge `174d02a`. backend 104 (92+12). Фінальне opus-рев'ю READY 0C/0I.

26. **OSM-енумераційний фід доменів** (crawler, перша половина тріщини #1 аудиту, [[ubd-crawler-osm-domain-feed]]) — самонаповнення `DomainRegistry` було голодне на нові домени (приплив залежав від мертвого DDG). Додано DDG-незалежний `OsmEnumerator` (один Overpass-запит на мережеві POI України з `website` + шумо-фільтр: `min_pois≥2`, дедуп за host, cap 500, блоклист-прескрін, `website`/`contact:website` fallback, fail→`{}`) + `OsmDomainFeed` (ротаційні website-кандидати з реюзнутого `BrandDomainCache`). Прапори `osm_feed_*` (дефолт ON) + `osm_feed_query_timeout=200` (>серверного `[timeout:180]`). `wiring._build_osm_feed` (best-effort refresh) + Runner **round-robin interleave фідів** (`zip_longest`, щоб OSM не голодив під `active_fetch_budget`). Нові домени — лише кандидати (precision-гейти+модерація нижче). Merge `0409d88`. crawler 400 (381+19). Фінальне opus зловило 3 Important (мої план-помилки: harvester-gate без osm/domain_feed; client-timeout 20с<180с; budget-starvation) — усі виправлено + re-review чисто. Ретайр мертвих DDG/SearXNG — окремий follow-up.

27. **Walker perf — скіп товарних сайтмапів + early-stop** (crawler) — deep-walk застрягав ~2 год на одному ретейлері, качаючи ~20 гігантських `sitemap-pt-product-*.xml` (SKU-каталог), чиї URL не проходять промо-фільтр. `collect_sitemap_urls` тепер пропускає child-сайтмапи з `product` у назві (промо-сторінки там не бувають) + зупиняється, щойно набрано `domain_page_cap` промо-URL. Якість-нейтрально (товарні сайтмапи й так давали ~0 промо). Merge `985e8fc`. crawler 403.

28. **Агрегатор як фід доменів** (crawler, veteranam follow-through, [[ubd-crawler-aggregator-domain-feed]]) — блоклистнуті каталоги ветеранських знижок (veteranam.info) як джерело **бізнес-доменів**, не оферів: harvester капчить вихідні бізнес-хости з блоклистнутих сторінок у `AggregatorDomainStore`, `AggregatorDomainFeed` ротаційно подає їх кандидатами → харвест сайту бізнесу → **first-party** офер → модерація. Аркуш агрегатора 0 оферів (інтерим-drop збережено, attribution.py недоторканий). Autofeed, blocklisted-only, persist+re-feed (дзеркало OSM-фіду). Прапори `aggregator_feed_*` (дефолт ON), byte-eq OFF. Merge `74d9c41`. crawler 420 (403+17). Фінальне opus зловило 1 Important (harvester-gate без aggregator_feed — та сама асиметрія, що в OSM) — виправлено + re-review чисто.

29. **Пасивна ре-модерація заапрувлених джерел** (backend+admin, [[ubd-approved-source-passive-remoderation]]) — заапрувлене джерело більше не пропонується повторно + при пасивному обході тільки *зміна* заводиться в модерацію. **Backend `create_offer`**: перевпорядкований crawler-дедуп — (1) незмінний `content_hash`+source → бамп `last_seen` (з ігнором expired-рядків); (2) змінена знижка/контент того самого source+`target_url_canonical` над **published**-офером → один лінкований **shadow** `pending_review` (`supersedes_offer_id`), старе published живе до рішення; ідемпотентно (≤1 shadow/parent); (3) ще-pending first-submission → in-place; (4) крос-джерельний canon-merge незмінний; (5) новий рядок. Реверт на живе значення дропає stale-shadow; реверт на expired-контент **реанімує** expired-рядок у shadow (обхід unique-constraint без INSERT). **`set_status`**: publish shadow → parent expired + `supersedes` очищається (ацикл-граф pending→published→null, не дає `CircularDependencyError` під selectin); reject лишає parent. **`OfferOut`** віддає `SupersedesOut`. **Серверний suggestion-guard** (`create_suggestion`): normalize_ref-звірка з активними Sources → 204 (єдиний чокпоінт, незалежний від клієнтського `known`). **Admin**: маркер «замінює #X (−10%→−20%)» у черзі (gated pending). Crawler незмінний. Merge `257237a`. backend 122 (106+16), admin 102 (97+5), crawler 420. Фінальне opus зловило Important (revert-after-approve тихо гасив живу картку) — виправлено (revive expired + clear-supersedes-on-publish) + re-review чисто. Жива Docker-перевірка: міграція `b2d4f6a80c11` застосована, guard 204/200 наживо, OfferOut-схема віддається.

30. **Точність екстрактора** (crawler, [[ubd-crawler-extractor-precision]]) — черга модерації заливалася сміттям: евристичний екстрактор емітив «офери» без знижки (нав-меню, проза, T&C-пункти «1.»/«2.», інстаграм-заклики), бо `heuristic.py` віддавав офер за trigger+target навіть коли `discount_type is None`. Рішення: **discount-гейт** `HeuristicExtractor(require_discount=False)` (class-default permissive/byte-eq) + `if self._require_discount and discount_type is None: return None`; config-прапор `require_discount` (**дефолт True**, 3 spots) → wiring → продакшн-гейт ON. + **розширення FREE-детекції** (безумовне, `content_hash` не зі знижки): `безоплатн`, `\b[ву] подарунок`/`\bу дарунок`, `даром`, `задарма`, `(?<!\d)0 грн/₴`, `_FIXED`+`гривень`; `безоплатн` також у `SEED_OFFER_TRIGGERS` (trigger-гейт передує FREE). Merge `0a5abf9`. crawler 433 (420+13). Фінальне opus рев'ю Ready 0C/0I; зловило Important (0-грн підрядок круглих цін «200 грн»→free) — виправлено lookbehind-ом. 1 Minor deferred (бонус/кешбек не в DISCOUNT_CTX). **Живий деплой через hot-copy stopgap** (pypi.org недосяжний → `docker build` заблоковано; трек без нових залежностей → `docker cp` 5 файлів + restart; гейт наживо перевірено; чергу очищено 18 сміттєвих); канонічний ребілд pending pypi.

31. **Admin edit links-sync + «Зберегти і опублікувати»** (backend+admin, [[ubd-admin-edit-links-sync-publish]]) — баг: правки «Сайт»/«Сторінка новини» в адмінці зберігались, але на public не зʼявлялись, бо `update_offer` писав лише offer-колонки, а public-картка рендерить лінки з `offer_links` (offer-колонки — лише фолбек). Фікс: `update_offer` синкає `offer_links` при зміні `provider`/`site_url`/`article_url` (0→створити / 1→оновити / >1→оновити той, що збігався зі старими; інші провайдер-лінки не чіпати). + кнопка **«Зберегти і опублікувати»** на сторінці редагування (не-published офери): `OfferForm` івент `submit-publish`→`OfferFormView` `update`→`publish`. Merge `c7c6a10`. backend 125 (122+3), admin 105 (102+3). Фінал-рев'ю inline (opus-агент впав на ліміті сесії) — Ready 0C/0I, 1 Minor (дублювання валідації). Задеплоєно наживо (backend+admin канонічний ребілд; link-sync перевірено з ревертом; crawler hot-copy уцілів). `image_url` вже offer-рівневе (доходить). Дроблення сторінки на офери — окрема робота [[ubd-todo-page-level-offer-identity]].

32. **Джерело тайтла офера (бізнес-опис) + OfferCard-фікси** (crawler+public, [[ubd-offer-headline-and-card-fixes]]) — тайтл-біля-бейджа був сміттєвим промо-фрагментом; тепер = **бізнес-опис сайту**. Crawler `WebsiteFetcher._extract_site_tagline` (ланцюг: хедер `.site-description`/`.tagline`/`[class*=slogan]` → футер `.tb-footer-desc`/`[class*=footer-desc]` → `<meta name=description>`, cap 160) → `RawItem.site_tagline`; `HeuristicExtractor` ставить його як `title`, але **`content_hash` рахує з промо-first-sentence** (churn-guard — наявні офери не пере-хешуються). Public `OfferCard`: `card__dtext` завжди (прибрано showTitle-дедуп), усі `offer_categories` чіпсами «Тематика» (було лише `[0]`). OfferDetailView вже коректний. Merge `73ba638`. crawler 439 (433+6), public 62 (60+2). Континуальний режим (без per-task checkpoint на прохання). Фінал opus Ready 0C/0I. Спостереження: наявні published тримають старий promo-title до зміни контенту/протухання. Задеплоєно (crawler+public канонічний ребілд).

33. **Ретайр SearXNG + B3c due-query walking** (crawler, [[ubd-crawler-news-exclusion]]) — SearXNG наживо діагностовано як **структурно непридатний** (усі апстрім-веб-рушії CAPTCHA-ять/throttle-ять наш вихідний IP; Bing відповідає, але на комерційні кириличні запити віддає **decoy-мотлох**; wikipedia марна для оферів). Тому повністю прибрано: `SearxngProvider`, searxng-гілку `build_search_plans`, `searxng_url` + мертвий `search_queries_per_pass` з config, docker-compose сервіс + `depends_on` + env, теку `searxng/`, згадки в RUN/README/.env.example. B2-машинерія двох провайдерів (block-partition/swap: `block_cursor`/`cycle`/`searxng_cursor` у `SearchState`, свап-цикл у `SearchPass`) **згорнута** до одно-провайдерного обходу по `grid_cursor`. DDG-шлях (RotatingDdgProvider/SearchCache/анти-throttle) — байт-ідентичний (з одним провайдером старий свап вже вироджувався). **B3c due-query walking:** `SearchState.is_fresh` + `QueryGrid.at`; `SearchPass` тепер щопрохід сканує від `grid_cursor` і бере лише **прострочені/нешукані (due)** фрази, пропускаючи кеш-свіжі (advance курсора за всі проглянуті), TTL з `search_cache_ttl_hours` → кожен прохід свіжа мережева робота, покриття само-вирівнюється під TTL; `ttl_seconds=0` = старий лінійний обхід (back-compat). Стан завантажується з legacy-ключами без міграції. crawler **543** (TDD, 9 задач: 6 retire+collapse, 3 B3c). Фінал opus READY 0C/1I(RESUME-doc стан)/3 Minor(2 deferred). Задеплоєно: канонічний ребілд crawler, searxng-контейнер зупинено+видалено, жива DDG-верифікація (без крашів; DDG у середовищному global-backoff — не наша регресія), жива due-walking-перевірка на реальному стані (від cursor=80 просканував 53, зібрав 15 due, пропустив 38 свіжих). NB live `crawler/.env` виправлено на `SEARCH_PROVIDERS=duckduckgo`.

34. **Авто-відхилення шумних оферів за хостом-джерелом + навчання блокліста** (backend, [[ubd-backend-auto-reject-blocked-source]]) — черга модерації забивалась шумом (офер 365: новина fraza.ua→хибний first-party+`free`). Аналіз 86 rejected vs 24 published: вирішальний сигнал — **хост-джерело** (published усі бізнес-домени). **Гейт** `create_offer`: crawler-офер, чий bare-host site_url/article_url/provider ∈ approved `blocked_hosts` (exact|suffix) → `rejected`, оминаючи дедуп-гілки 2/3/4 (гілка-1 ідемпотентності лишається). `_source_host` рахує хостом лише значення з крапкою (provider — вільний текст). **Навчання** `set_status`: хост із ≥2 rejected і 0 published → `auto_block` (гард захищає дуал-статусні бізнес-хости). **Seed-міграція** `d4e6f8a0b2c4`: 22 куровані новинні/соц-хости. Реюз `blocked_hosts` (краулер уже no-fetch-ить approved). backend **177** (TDD, 5 задач). Фінал opus зловив Important (гейт гардив гілку-1→re-crawl passive=dup INSERT/500) — виправлено. ff-merge `e49b788` (НЕ pushed). Задеплоєно+жива e2e (fraza.ua→rejected, reima.ua→pending). Свідомо поза: дублікати, charity/generic-без-знижки, екстрактор-точність.

35. **Точність free + provider=назва** (crawler, екстрактор, [[ubd-crawler-free-precision-provider-name]]) — два компоненти в `heuristic.py`: (1) **free-proximity gate** — `free` зараховується лише коли free-тригер І термін-аудиторія в тексті **того самого блока** (`_has_audience_in_text=bool(classify(text,TARGET_LEXICON))`), а не лише в provider/site_name; прибирає хибний free з generic-сторінок («Умови доставки», «Про команду»); на fail падає в elif percent/fixed. (2) **provider-поле = назва компанії/сайту** (`item.site_name`, фолбек хост); churn-guard: `content_hash`/`blob` лишаються на хості. crawler **549** (TDD, 3 задачі). ff-merge `3d10d2e` (НЕ pushed). Компроміс: великий `<article>`-блок грубший (новинний підклас ловить хост-гейт #34).

**Операційні/UI фікси цієї сесії (2026-07-23, кожен окремий merge):** admin — URL у «Нотатці» запропонованих джерел як лінк + вкладки оферів «Опубліковані/На модерації» (`6703d14`); veteranam salvage-флуд спинено (блоклистнутий агрегатор → drop без salvage, `c5540e4`); ручне додавання хоста в блокліст через адмінку (`POST /admin/host-candidates`→approved, `54dde67`). Живий Docker-стек піднято (active_discovery=ON, 30-хв цикл); наскрізь перевірено — active+passive+feeds виробляють офери, стійкий до мережевих збоїв.

**Свідомо НЕ роблено:** C2 (сегментація тексту в блоці) — реальні дані показали непотрібність; деталі у пам'яті [[ubd-discovery-plan]].

## ⚠️ Відкриті пункти (для наступних сесій)

- **Пошук: SearXNG ретайрнуто (трек #33), DDG лишається opt-in (середовищно деградований):** активний DDG-пошук глушать rate-limit/CAPTCHA; **Brave API відкинуто користувачем**. **SearXNG прибрано повністю** — на відміну від DDG його деградація **структурна, не оборотна** (скрапер тих самих ворожих рушіїв; наш IP отримує CAPTCHA або decoy), тож degraded≠dead тут не діє (докази наживо, трек #33). DDG active search — легітимний **opt-in** канал (`active_discovery` дефолт OFF, анти-throttle машинерія, тепер ще й B3c due-walking): деградований *середовищем*, оборотно — **НЕ ретайрити** (query-grid/site:/DDG лишаються opt-in — degraded≠dead, [[feedback-preserve-working-structure]]). Тріщину #1 закрив OSM-фід (трек 26) = DDG-незалежний приплив.
- **Атрибуція:** новинні/держ/агрегатор-сайти досі просочуються як фейкові провайдери (дають «шумні» багатокатегорійні офери). Посилення — відкладено.
- **Відкладене:** target-вісь лишається курованою; IG/FB-харвест; новинні Telegram-канали.
- **Дані (2026-07-27):** у compose-БД `ubd` — 5 published + 1 rejected оферів; **чергу модерації очищено на запит** (видалено 28 pending offers + 9 pending suggested-sources). Краулер репопулює чергу наступними проходами.
- **Docker (2026-07-27):** `backend`+`admin` перезібрані цієї сесії (трек 29: міграція `b2d4f6a80c11` застосована, маркер у адмінці). **`public` образ досі застарілий** (не перезбираний після responsive-треку) — живий `:8080` НЕ показує адаптив. Для перевірки: `docker compose build public && docker compose up -d`.
- **Краулер працює безперервно:** `ubd_probe-crawler-1`, `CRAWL_INTERVAL_SECONDS=1800` (30-хв loop), errors=0, self-growing ротація активна (`grid_cursor`, `site_cursor`/`approved_cursor`, query-cache 219, brand/osm/aggregator/domain-registry фіди персистять).

**Аудит цілісності (2026-07-23, [[ubd-design-for-whole-picture]]):** пройдено весь проєкт. Геп #2
(крос-платформний дедуп) — **закрито** (трек 25). Тріщина #1 (discovery залежав від деградованого DDG
без DDG-незалежного припливу) — **ЗАКРИТО** OSM-фідом (трек 26): тепер є незалежний приплив доменів.
DDG active search лишається легітимним **opt-in** каналом — **НЕ ретайрити** (degraded≠dead;
[[feedback-preserve-working-structure]]). Ще відкрито (необовʼязкове): атрибуція інертна без людського
сіду (cold-start); асиметрія осей (target курована vs offer self-growing).

**Наступний трек (рекомендація):** усе self-growing discovery + маркетинг-лексикон + **domain-rating**
+ **site:** + **канонічний дедуп** + **OSM-фід** зроблено. Тріщину #1 закрито, гепи аудиту закрито.
Обовʼязкових треків **немає**. Опційні P3: бренд-якорні запити; LLM-хвіст перефразувань (офлайн,
injection-hardened); cold-start атрибуції. Деталі — [[ubd-crawler-discovery-scaling-brainstorm]].
Альтернативи: посилення атрибуції проти медіа-провайдерів; IG/FB-харвест. Обовʼязкових немає.

**Як запускати:** повний довідник — `RUN.md` (окремо/разом, краулер, активний пошук,
потік у адмінку); Docker-деталі — `README-docker.md`.

**Тести (перевірено 2026-07-23):** admin **97**, public **60**, crawler **420**, backend **106** —
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
