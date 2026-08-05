# Auto-reject noise offers by source host + learn blocklist from rejections

**Дата:** 2026-08-05
**Гілка:** `feat/backend-auto-reject-blocked-source` (від `main` 00cf506)
**Тип:** backend-only. Crawler/admin/public не змінюються (краулер уже споживає approved `blocked_hosts`).

## Мотивація (на фактах з живої БД)

Черга модерації забивається шумом краулера. Приклад — офер 365: новинна стаття на **fraza.ua**
(«Доставка суші та піци…»), з якої атрибуція «врятувала» бізнес-домен uglovoy.com.ua і екстрактор
видав хибний `free`. Аудиторія/знижка нерелевантні.

Аналіз **усіх 86 rejected проти 24 published**:
- **Вирішальний сигнал — ХОСТ-ДЖЕРЕЛО, не аудиторія** (усі 24 published і всі 86 rejected мають
  аудиторію — марний сигнал).
- Усі **24 published** — з бізнес-доменів (boxraw, imd.ua, reima.ua, dobrobut, camotec…).
- Відхилені: (1) **новинні/медіа-джерела** (fraza.ua, znaj.ua, epravda.com.ua, focus.ua, kosht.media,
  24tv.ua, unn.ua, parlament.ua, rubryka.com, ogo.ua, izum.ua, nefterynok.info, uc.kr.ua,
  pravdahub.com.ua, ukrainianwall.com, dtkt.ua, prostir.ua…) — найбільший клас; (2) **соц/утиліта як
  `provider`** (api.whatsapp.com, google.com, news.google.com, linkedin.com, linktr.ee, addtoany.com)
  — сміття атрибуції; (3) **дублікати** плаузибельних оферів (reima×2, batart×4…) — це дедуп, НЕ хост.

## Мета

Авто-відхиляти офери класів (1)–(2) за хостом-джерелом і **вчити блокліст із рішень модератора**,
не чіпаючи published-клас (нуль хибних блоків).

## Дизайн

Реюз наявної таблиці `blocked_hosts` (status pending/approved/rejected; `list_approved_hosts`;
`add_manual`; bare-host норм. `_bare_host`). Краулер уже тягне approved через internal
`list_blocked_hosts` → авто-заблоковані хости він і фетчити перестане (belt-and-suspenders).

### Компонент 1 — Гейт авто-відхилення (`backend/app/crud/offer.py::create_offer`)
На початку `create_offer` обчислити `blocked = (created_by == CreatedBy.crawler) and
_blocked_source_host(db, data) is not None`, де хелпер `_blocked_source_host(db, data) -> str | None`
повертає перший із bare-хостів {`data.site_url`, `data.article_url`, `data.provider`}, що ∈
`set(blocked_host.list_approved_hosts(db))` (або None).
- Якщо `blocked`: **пропустити дедуп-гілки 1–4** (обгорнути їх у `if not blocked:`), щоб блокований
  лінк не влився в published-офер, і піти на звичайне створення (наявний `Offer(...)` шлях), але зі
  `status = OfferStatus.rejected` (реюз коду створення, без дублювання).
- Офер зберігається повністю (title/discount/links) як аудит-слід, лише зі status=rejected.

Гейт спрацьовує лише для crawler-оферів; ручні (admin) офери не чіпає (`blocked` там False).

### Компонент 2 — Seed (Alembic-міграція)
Вставити в `blocked_hosts` (status=approved, reviewed_by=NULL, ratios/support=0) курований список
**чистих** новинних/медіа + соц/утиліта хостів (жоден НЕ має published-офера — перевірено):
`fraza.ua, znaj.ua, epravda.com.ua, focus.ua, kosht.media, 24tv.ua, unn.ua, parlament.ua,
rubryka.com, ogo.ua, izum.ua, nefterynok.info, uc.kr.ua, pravdahub.com.ua, ukrainianwall.com,
dtkt.ua, api.whatsapp.com, news.google.com, google.com, linkedin.com, linktr.ee, addtoany.com`.
Ідемпотентно (INSERT IGNORE / ON DUPLICATE). Спірні (prostir.ua, afterfront, digital-front,
savelife, maibutniefund) свідомо НЕ сідяться — їх підбере навчання.

### Компонент 3 — Авто-навчання (`backend/app/crud/offer.py::set_status`, перехід у `rejected`)
Після встановлення `rejected`:
- кандидат-хости = `{_bare_host(site_url), _bare_host(article_url), _bare_host(provider)}` \ {порожні,
  вже-approved};
- для кожного хоста `h` порахувати офери, де `h` ∈ bare-host будь-якого з трьох полів, за статусом:
  якщо **rejected ≥ 2 і published == 0** → нова crud-функція
  `blocked_host.auto_block(db, h)` — upsert хоста у `status=approved` з `reviewed_by=None`
  (системний авто-блок, на відміну від `add_manual`, що вимагає людину). Реалізація підрахунку:
  SQL-prefilter `LIKE %h%` по трьох полях, потім точна bare-host звірка в Python (таблиця оферів
  мала); дедуп по offer.id.
- Гард **published == 0** — критичний: захищає дуал-статусні бізнес-хости (reima/batart/boxraw).
- Поріг `rejected >= 2` — константа модуля (`_AUTOBLOCK_MIN_REJECTS = 2`).

Навчання викликається на будь-якому переході в rejected (і ручний reject, і гейт-авто-reject — але
гейт-хости вже approved, тож не ре-тригерять). Best-effort: помилка навчання не валить reject.

## Точність / безпека
- 24 published — усі бізнес-домени, нема в seed, нема з published==0 → **нуль хибних авто-блоків**.
- Гейт+seed прибирає новинний клас негайно; навчання добирає хвіст (prostir×8 тощо) при ≥2/0.
- Reversible: помилковий блок → admin «Медіа-блокліст» reject (наявний UI трек #22).

## Поза скоупом (свідомо)
Дублікати (дедуп), charity-фонди/generic-сторінки без знижки (savelife, funt.coffee) — інші сигнали,
окремий трек. Auto-publish не вводимо (лишається людина). Екстрактор-точність (хибний `free`) — окремо.

## Тести (backend pytest; потребує mysql-container :3306)
- гейт: crawler-офер із site_url на approved-хості → status=rejected, не мерджиться;
- гейт: crawler-офер із чистим бізнес-хостом → pending_review (незмінно);
- гейт: перевірка provider-хоста (google.com) → rejected;
- гейт не чіпає admin-оферів;
- навчання: 2-й reject хоста з 0 published → хост стає approved;
- навчання: reject хоста, що має published-офер → НЕ блокується (guard);
- навчання: <2 rejected → не блокується;
- seed-міграція: upgrade вставляє хости approved, ідемпотентно.
