# Backend: канонічний дедуп оферів (`target_url_canonical`)

**Дата:** 2026-07-23
**Трек:** закриття гепу #2 з аудиту цілісності ([[ubd-design-for-whole-picture]]). Гілка `feat/backend-dedup-canonical` від `main`.
**Скоуп:** лише `backend/`. Без crawler/admin/public-змін.

## Проблема й мета

Мердж оферів (`OfferLink`) матчить по **сирому** `Offer.target_url` ([backend/app/crud/offer.py:37](backend/app/crud/offer.py)).
Наслідки:
- Офери, що різняться лише `utm_*`/click-id (`fbclid`, `gclid`, …), `www.` чи схемою http/https, **не мерджаться** → дублі.
- Канонікалізація дубльована в двох кодобазах (`backend/app/core/urlnorm.py`, `crawler/.../providers._normalize_url`), і жодна не стрипає click-id.

**Мета:** ввести спільний бекенд-обчислюваний ключ `target_url_canonical` (єдине джерело істини), дедупити мердж по ньому. Сирий `target_url` лишається для кліку.

## Зафіксовані рішення (незмінні, з брейншторму)

- Скоуп = лише спільний нормалізований `target_url`.
- Модель = нова колонка `Offer.target_url_canonical` (сирий `target_url` лишається для кліку/показу).
- Наявні дані = backfill canonical **без** ретро-мерджу (наявні дублі не збираємо).

## Затверджені рішення (брейншторм 2026-07-23)

1. **Джерело істини = бекенд.** `create_offer` обчислює canonical із сирого `target_url` для **всіх** оферів (краулер і адмін). Краулерний `_normalize_url` лишається лише для класифікації кандидатів — він **не** дедуп-ключ.
2. **Агресивність:** прибрати `www.`; злити http↔https (схема не входить у ключ). Плюс базовий набір: не-http(s)→`None`, lowercase host, прибрати fragment/port/userinfo, `rstrip` path `/`, викинути `utm_*`+курований список click-id, решту query відсортувати.
3. **Merge-політика — зберегти поточну.** Canonical обчислюється/зберігається для всіх (у т.ч. адмін). Адмін-create дедуп **не** запускає (авторитетний). Краулер-create шукає збіг серед **усіх** оферів (у т.ч. адмінських) за canonical і доливає `OfferLink` (поля не перезаписує). Єдина зміна — ключ збігу raw→canonical.

## Архітектура

### 1. Канонікалізатор — `backend/app/core/urlnorm.py`

Поряд із наявним `normalize_source_ref` (спільний модуль канонікалізації бекенду, не нова копія):

```python
_TRACKING_PARAMS = frozenset({
    "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "fbclid", "yclid", "msclkid",
    "twclid", "ttclid", "igshid", "mc_eid", "mc_cid", "_openstat", "vero_id",
    "oly_enc_id", "oly_anon_id", "icid", "scid", "srsltid", "spm",
})

def canonicalize_target_url(url: str) -> str | None:
    """Scheme-less, www-less dedup key: lowercased host (no port/userinfo, www. dropped),
    path without trailing slash, tracking params (utm_*/click-ids) stripped, rest sorted.
    http↔https collapsed (scheme omitted). Returns None for non-http(s)/junk."""
    if not url:
        return None
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = (p.hostname or "").removeprefix("www.")
    if not host:
        return None
    kept = sorted((k, v) for k, v in parse_qsl(p.query)
                  if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS)
    query = urlencode(kept)
    path = p.path.rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")
```

Приклади: `https://www.okko.ua/promo/?utm_source=fb&fbclid=x` і `http://okko.ua/promo?fbclid=y` → обидва `okko.ua/promo`. `https://shop.ua/p?id=5&utm_x=1` → `shop.ua/p?id=5`.

### 2. Модель + міграція — `backend/app/models/offer.py`, `backend/alembic/`

Колонка після `target_url`:
```python
target_url_canonical: Mapped[str | None] = mapped_column(String(1024), nullable=True)
```
Індекс у `__table_args__`:
```python
Index("ix_offers_target_url_canonical", "target_url_canonical", mysql_length=255),
```
Alembic-ревізія поверх поточного head: `add_column` + `create_index`, потім **data-backfill** — для кожного офера з `target_url` проставити `canonicalize_target_url(target_url)`. Функцію імпортувати з `app.core.urlnorm` (стабільна, детермінована; БД зараз 0 оферів). **Без** unique-констрейнта, **без** ретро-мерджу. `downgrade` = `drop_index` + `drop_column`.

### 3. `create_offer` — `backend/app/crud/offer.py`

- Обчислити один раз `canon = canonicalize_target_url(data.target_url)`.
- `content_hash`-стадія — без змін.
- `target_url`-стадію замінити на canonical-стадію:
```python
if created_by == CreatedBy.crawler and canon:
    existing = (db.query(Offer).filter(Offer.target_url_canonical == canon)
                .order_by(Offer.id).first())          # oldest match, deterministic
    if existing is not None:
        already = any(l.provider == data.provider and l.site_url == data.site_url
                      and l.article_url == data.article_url for l in existing.links)
        if not already:
            existing.links.append(_mk_link())
        existing.last_seen_at = datetime.utcnow()
        db.commit(); db.refresh(existing)
        return existing
```
- У конструкторі `Offer(...)` додати `target_url_canonical=canon` (для всіх created_by).

### 4. `update_offer` — консистентність колонки

Після циклу `setattr`, коли редагується `target_url`:
```python
if "target_url" in payload:
    obj.target_url_canonical = canonicalize_target_url(obj.target_url)
```

## Межі скоупу (що НЕ змінюється)

- `OfferCreate`/`OfferBase`/`OfferOut` — без canonical (суто внутрішня).
- Public — клік по сирому `target_url`.
- `content_hash`-стадія дедупу — без змін.
- Без unique-констрейнта, без ретро-мерджу.
- Крос-компонентну консолідацію `normalize_source_ref`/`_normalize_url` свідомо НЕ робимо (інша задача, YAGNI).

## Тести (backend, pytest; потребує `mysql-container` на :3306)

1. **`test_urlnorm.py`** — `canonicalize_target_url`: www-strip; http↔https-злиття; utm_*+click-id strip; сортування решти query; trailing-slash; порт/userinfo; не-http→`None`; порожнє→`None`; збереження значущих query-параметрів.
2. **Дедуп (crud/API)** — два краулер-офери, чиї `target_url` різняться лише utm/click-id/www/схемою → **один** офер + другий як `OfferLink`; `target_url_canonical` збережено. Різний canonical → окремі офери.
3. **Адмін не дедупить** — два адмін-офери з тим самим canonical → **два** рядки; але canonical у кожного проставлено.
4. **Крос-created_by мердж** — краулер-офер із canonical наявного **адмін**-офера доливає лінк у нього (поточна поведінка).
5. **`update_offer`** — зміна `target_url` перераховує canonical; зміна інших полів — ні.
6. **Backfill** — вставити рядок офера з `target_url` і `target_url_canonical=NULL` (сирим insert), викликати backfill-логіку міграції (винести у функцію, що приймає connection) → canonical проставлено; рядок без `target_url` лишається NULL.

## Перевірка завершення

- backend-тести зелені (baseline 92 + нові), `pytest -q` з `backend/` (потрібен `mysql-container`).
- Alembic upgrade/downgrade чисто на порожній та заповненій БД.
- Фінальне opus whole-branch рев'ю перед merge.
