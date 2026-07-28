# Джерело тайтла офера (бізнес-опис) + public OfferCard-фікси

**Дата:** 2026-07-28
**Гілка:** `feat/offer-headline-and-card-fixes`
**Скоуп:** crawler (джерело тайтла) + public (OfferCard). Backend/схема/admin не чіпаємо.

## Проблема

1. **Тайтл-біля-бейджа = сміттєвий промо-фрагмент.** `offer.title` = `_title_from(text)` (перше речення промо-блоку), напр. «Знижки для курсантів...». Треба **стабільний бізнес-опис** (як `.tb-footer-desc` на rezervist: «Rezervist - магазин тактичного, військового одягу та спорядження...»).
2. **На картці видно лише 1 тематику** — `OfferCard.vue` `meta` бере `offer_categories?.[0]?.name` (лише перша).
3. **`card__dtext` не на всіх картках** — `showTitle` навмисно ховає тайтл, коли опис починається з нього (дедуп); для крауловских оферів title=перше-речення-body → ховається на більшості.

*(OfferDetailView вже коректний: тайтл показує завжди (рядок 62), усі offer_categories чіпсами (74-76) — не чіпаємо.)*

## Рішення

### Компонент A — джерело тайтла (crawler)

**Ланцюг джерела бізнес-опису** (перший непорожній), у `fetchers/website.py` нова `_extract_site_tagline(tree)`:
1. **Хедер біля лого / tagline:** `.site-description`, `.tagline`, `[class*="slogan"]` (перший непорожній текст).
2. **Футер-опис:** `.tb-footer-desc`, `[class*="footer-desc"]`.
3. **`<meta name="description">`** — надійний загальний фолбек.
4. *(інакше None → у екстракторі падаємо на промо-first-sentence)*

Результат (trim, cap ~160 символів по word-boundary) кладеться на кожен `RawItem.site_tagline` (нове поле в `models.py`, як `site_name`).

**У `extract/heuristic.py`** розчепити hash і дисплей (щоб НЕ було churn'у наявних оферів):
```python
promo_title = _title_from(text)
title = (item.site_tagline or "").strip() or promo_title      # дисплей: бізнес-опис або фолбек
...
content_hash=content_hash(promo_title, provider, text),        # HASH на промо-title — байт-ідентичний поточному → 0 churn
```
Тобто `content_hash` лишається на промо-first-sentence (дедуп незмінний), а `title` стає бізнес-описом. Жодних змін дедупу/re-moderation.

### Компонент B — public OfferCard (`public/src/components/OfferCard.vue`)

- **(b) Тайтл завжди:** `card__dtext` `v-if="offer.title"` (прибрати `showTitle`-дедуп + `norm`-хелпер). Оскільки title тепер бізнес-опис ≠ промо-description, візуального дубля нема; для fallback-оферів (title=промо) дубль приймаємо (за рішенням користувача — показувати завжди).
- **(a) Усі тематики чіпсами:** прибрати `offer_categories[0]` з `meta` (лишити лише `location`); додати блок-чіпси «Тематика» (дзеркало «Для кого») з усіма `offer_categories`.

## Тести

- **crawler:** `_extract_site_tagline` — пріоритет хедер→футер→meta, cap, порожньо→None; `WebsiteFetcher` кладе `site_tagline` на RawItem; `heuristic.extract` — `title = site_tagline` коли є, інакше `_title_from`; **`content_hash` байт-ідентичний** незалежно від site_tagline (регрес-замок проти churn).
- **public:** OfferCard рендерить усі offer_categories чіпсами; `card__dtext` показано щоразу коли `title` непорожній (навіть якщо опис починається з нього); meta більше не містить категорію; `npm run build`.

## Не-скоуп (YAGNI)
- OfferDetailView (вже коректний).
- Backend/схема (title — наявне поле).
- Дроблення сторінки на офери — окремий трек [[ubd-todo-page-level-offer-identity]].
