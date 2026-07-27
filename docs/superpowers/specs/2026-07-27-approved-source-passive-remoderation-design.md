# Пасивна ре-модерація заапрувлених джерел

**Дата:** 2026-07-27
**Гілка:** `feat/approved-source-passive-remoderation`
**Скоуп:** backend (офер-дедуп, suggestion-guard, міграція), admin (shadow-контекст). Краулер **не змінюється**.

## Проблема

Заапрувлене джерело далі пасивно обходиться (website → `DomainWalker` deep-walk; telegram → fetch), щоб ловити зміни. Бажана поведінка:

- **Нема змін** → тихо оновити `last_seen_at`, без нового елемента на модерацію.
- **Зʼявився новий офер** → офер у чергу модерації.
- **Змінилася поточна знижка/контент наявного офера** → у чергу модерації (ре-модерація), але **без дублів** і зі збереженням старого published на сайті до підтвердження.
- Заапрувлене джерело **не пропонується повторно** як suggested-source.

### Поточні діри

1. **Зміна знижки губиться.** У `create_offer` (backend/app/crud/offer.py:29-51) крок canon-merge (рядки 40-51) стоїть **після** content_hash. Якщо знижка змінилась → `content_hash` інший (крок content_hash промах) → але `target_url_canonical` той самий → canon-крок **тихо змерджить у наявний published-офер** (доліпить лінк, бампне `last_seen`), нового pending **не створить і `discount_value` не оновить**. Зміна з того самого джерела просто зникає.
2. **Suggestion-guard лише клієнтський.** Серверний `create_suggestion` (backend/app/crud/suggested_source.py:14-19) дедупить **тільки проти інших SuggestedSource-рядків**, НЕ проти активних `Source`. Гарантія «не пропонувати вже-активне джерело» тримається на крихкому клієнтському `known`-снімку в runner/harvest; при його застарінні/розбіжності нормалізації pending-suggestion для вже-активного джерела просочиться.

## Що вже працює (не чіпати)

- **Незмінний офер → тихий бамп.** content_hash+source_id збіг (offer.py:29-38) → `last_seen_at` бамп, без нового рядка. Published-офер зберігає `content_hash` через межу апруву, тож re-walk незмінного published теж потрапляє сюди. ✅
- **Крос-джерельний link-merge** (агрегатор/крос-платформ, різні `source_id`, той самий canon) → залишається як є.
- **Клієнтський `known`-дедуп** у runner.py:56 / harvest.py:43,113 — лишається як перша лінія; серверний guard додається як defense-in-depth-чокпоінт, не заміна.

## Рішення

### Компонент A — детекція зміни в `create_offer`

Новий порядок гілок для crawler-сабмішена (`created_by == crawler`, `source_id` заданий):

1. **Незмінний** — `content_hash`+`source_id` збіг → бамп `last_seen_at`, return existing. *(наявна поведінка)*
2. **Зміна того самого офера (НОВЕ).** content_hash не збігся, але існує **published**-офер `P` із тим самим `source_id` **і** тим самим `target_url_canonical`:
   - Це зміна `P`. Знайти наявний shadow: `pending_review`-офер із `supersedes_offer_id == P.id`.
     - Знайдено й `content_hash` збігається з новим → бамп shadow.`last_seen_at`, return shadow (ідемпотентно).
     - Знайдено, але hash інший (знижка змінилась ще раз до дій модератора) → оновити поля shadow до найсвіжішого контенту (title/description/discount_*/target_url/links/категорії/`content_hash`), бамп, return.
     - Не знайдено → створити shadow `pending_review`-офер з новим контентом і `supersedes_offer_id = P.id`.
   - **У всіх під-випадках:** бампнути `P.last_seen_at` — офер ще живий на сайті, не дати `expire_stale` погасити його, поки модератор думає.
3. **«Parent» ще pending.** Якщо існує офер із тим самим `source_id`+`canon`, але він сам `pending_review` (перший сабмішн ще не заапрувлений) — не shadow, а оновити той pending in-place до найсвіжішого контенту (він ще не публічний, дублювати нема сенсу). return.
4. **Крос-джерельний merge** — canon-збіг, але інший/None `source_id` → наявна поведінка (доліпити лінк, бамп). *(без змін)*
5. **Новий офер** — жодного збігу → новий `pending_review`-рядок. *(наявна поведінка)*

**Ключ розрізнення** гілки 2/3 від гілки 4 — збіг `source_id`: та сама реколонка того самого джерела = зміна власного офера; інший source = крос-джерельний merge.

**Порядок реалізації:** гілки 2/3 мають спрацьовувати **перед** наявним canon-merge-кроком, інакше canon-merge знову проковтне зміну (діра #1).

### Компонент B — approve/reject shadow

Хук у `set_status` (backend/app/crud/offer.py), яким користується admin publish/reject:

- **Publish** офера, що має `supersedes_offer_id = P.id`: shadow → `published`; `P` → `expired` (у тій самій транзакції). Публіка бачить нову знижку, старий рядок гасне. Жодного дубля published.
- **Reject** shadow (`rejected`): parent `P` недоторканий, лишається `published`.
- Публіка не чіпається до publish (shadow = `pending_review`, не публічний).

### Компонент C — схема

Alembic-міграція: колонка `offers.supersedes_offer_id INTEGER NULL`, self-FK → `offers.id` (ON DELETE SET NULL). `OfferOut` (admin-серіалізатор) віддає `supersedes_offer_id` + короткий контекст parent-а (id, поточні `discount_type`/`discount_value`, title) для показу diff у черзі.

### Компонент D — серверний suggestion-guard

`create_suggestion` перед створенням pending нормалізує `(type, url_or_handle)` і звіряє з **активними `Source`**: якщо вже є активне джерело з тим самим нормалізованим ref — тихо повернути без нового pending (як і при наявному-SuggestedSource-збігу). Backend-side normalize дзеркалить crawler-ський `normalize_ref` (lower; strip scheme/`www.`/платформ-префікс/`@`/trailing `/`). Активних джерел небагато → нормалізація в Python по завантаженому списку прийнятна.

### Компонент E — admin UI

У черзі модерації офер із `supersedes_offer_id` показує маркер **«замінює офер #X (було −10% → стане −20%)»**, щоб модератор бачив, що це ре-модерація, а не новий офер. Кнопки approve/reject уже є — семантика supersede живе в backend `set_status`.

## Крайові випадки

- **Повільний модератор.** Кожен re-walk зі зміною бампає `P.last_seen_at` → `P` не протухне, поки висить shadow.
- **Знижка змінилась двічі до модерації.** Один shadow на parent; другий re-walk оновлює той самий shadow до найсвіжішого (не плодить).
- **Reject shadow, потім знову зʼявляється та сама зміна.** Наступний re-walk не знайде shadow (він `rejected`, не `pending_review`) → створить новий shadow. Прийнятно: модератор відхилив, але сайт досі показує зміну → варте повторного показу. *(Ідемпотентність — лише проти живого `pending_review`-shadow.)*
- **Telegram-джерела** без `target_url_canonical`: гілка 2 вимагає canon-збіг; якщо telegram-офер не має canonical target — зміна піде звичайним content_hash-шляхом (новий pending_review-рядок як «новий офер»). Type-agnostic: логіка кейтиться на `source_id`+`canon`, обмежень за типом нема.

## Тестування

- **backend (+нові):** content_hash-незмінний-бамп (регрес); зміна published → shadow з `supersedes_offer_id`; ідемпотентність (2-й walk оновлює той самий shadow); parent.last_seen бамп; parent-ще-pending → in-place; крос-джерельний merge не регресить; publish-supersede гасить parent; reject-shadow лишає parent; guard skip проти активного Source; guard дозволяє нове джерело.
- **admin (+):** маркер supersede у списку/деталях; approve/reject shadow крізь UI.
- **crawler:** незмінний, baseline **420** має лишитися зеленим (перевірка сумісності payload/поведінки).

## Нескоуп (YAGNI)

- Жодних змін у краулері (детекція суто backend-side).
- Без окремої таблиці «історії змін» — shadow-офер сам є записом запропонованої зміни.
- Без авто-approve змін — усе через модератора (вимога задачі).
