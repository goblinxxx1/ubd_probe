# Дедуп дублікатів discovered-оферів по промо-сторінці

Дата: 2026-08-05
Трек: чистка черги модерації від шуму краулера (#2 «Дедуп дублікатів»)
Гілка: `track-dedup-duplicates`

## Проблема

Модератор регулярно відхиляє кілька майже-однакових записів з однієї промо-сторінки:
`reima×2, batart×4, kupola×5, loadup×4, prostir×8`. Це шум, який роздуває чергу.

### Корінь (діагностика)

Page-level dedup (Трек#6) — це **in-memory groupby по сирому `article_url`** у межах
одного batch ([harvest.py:134](../../../crawler/crawler/discovery/harvest.py),
[runner.py:195](../../../crawler/crawler/runner.py)). Він не канонізує URL і не бачить
попередні прогони.

Реальний дедуп — у бекенді ([offer.py `create_offer`](../../../backend/app/crud/offer.py)),
і там три сліпі плями саме для дублів **активного пошуку**:

1. **Офери активного пошуку йдуть із `source_id=None`**
   ([harvest.py:101](../../../crawler/crawler/discovery/harvest.py) — `{"id": None}`).
   Гілки дедупу по `article_url_canonical` (гілки 2 і 3) гейтяться умовою
   `source_id is not None` → для discovered-оферів **пропускаються повністю**.
2. Лишається гілка 1 (content_hash) — короткозамикає **тільки при байт-ідентичному**
   `content_hash` (title+provider+body). Між прогонами тіло/лейбл знижки/provider
   дрейфують → хеш міняється → не ловить.
3. **Жодна гілка не короткозамикає повторну сторінку проти вже `rejected` запису.**
   Тому та сама сторінка з 4 прогонів із дрейфом контенту = 4 нових pending →
   модератор відхиляє кожен окремо.

`#34` (auto-block хоста після ≥2 rejected) частково гасить це, але грубо: блокує
**весь хост** і лише після 2 відхилень. Дедуп сторінки б'є точніше — та сама фізична
промо-сторінка = один запис у черзі, з першого разу, не чіпаючи інші сторінки хоста.

## Рішення

Одна нова гілка в `create_offer`, симетрична гілкам 2/3, але для **`source_id IS NULL`**
(discovered-офери активного пошуку). Розташування — **після гілки 1** (content_hash)
і **перед гілкою 4** (target-merge): ідентичність сторінки сильніша за target-merge.

### Логіка

```python
# N) discovered-офер (активний пошук, source_id=None): та сама промо-сторінка вже відома
#    -> короткозамкнути (skip). Не гейтимо `not blocked`: дублі blocked-rejected із дрейфом
#    content_hash теж мають злипатися по сторінці, а не INSERT-итися знову.
if crawler and canon_article and source_id is None:
    existing = (db.query(Offer)
                .filter(Offer.source_id.is_(None),
                        Offer.article_url_canonical == canon_article,
                        Offer.status != OfferStatus.expired,
                        Offer.supersedes_offer_id.is_(None))
                .order_by(Offer.id).first())
    if existing is not None:
        existing.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing            # SKIP: вміст не оновлюємо, новий рядок не плодимо
```

### Семантика за статусом існуючого

| Статус existing | Дія | Чому |
|---|---|---|
| `pending_review` | skip, bump last_seen | Модератор бачить один запис; вміст не чіпаємо (вимога користувача — «не оновлювати, пропускати джерело») |
| `rejected` | skip, bump last_seen | Дубль не повертається в чергу — закриває batart×4/kupola×5/prostir×8 |
| `published` | skip, bump last_seen | freshness-сигнал; зміну знижки ловить пасивний прогін через існуючий shadow-механізм — активний краулер сюди не лізе |
| `expired` | НЕ ловимо (фільтр `!= expired`) | Дзеркалить гілку 1: revert до простроченого має пройти далі на переINSERT/re-moderation |

### Розділення ролей (підтверджено з користувачем)

- **Активний краулер** (`source_id=None`): відома сторінка → просто skip, нічого не плодить. Ця гілка.
- **Пасивний прогін** (source-bound, `source_id` заданий): раз на прогін перевіряє зміну
  знижки → існуючий shadow-механізм (гілка 2). Не чіпаємо.

## Що НЕ робимо (YAGNI / межі скоупу)

- **Crawler-side стан або канонікалізація in-memory groupby** — не потрібні: бекенд
  stateless-надійно скіпне після канонікалізації URL. Єдине джерело істини — БД.
  (У межах одного прогону байт-різні форми теж пройдуть через бекенд і злипнуться.)
- **Shadow-ре-модерацію для discovered `published`** — поза скоупом. Пасивний прогін
  покриває зміни для оферів, що стали source-bound.
- Гілки 2/3/4 і гілку 1 **не чіпаємо** — лише додаємо нову гілку.

## Технічні передумови (перевірено)

- `canonicalize_target_url` ([urlnorm.py:30](../../../backend/app/core/urlnorm.py)) вже
  зливає `www`/`utm_*`/click-id/пагінацію/trailing-slash і http↔https → байт-різні форми
  тієї ж сторінки дають один `article_url_canonical`.
- Індекс `ix_offers_article_url_canonical` існує → lookup швидкий.
- Unique-constraint лише `(source_id, content_hash)` → нова гілка йому не суперечить.
- Міграції не потрібні (використовуємо наявну колонку `article_url_canonical`).

## Тести

Новий файл `backend/tests/test_offer_discovered_dedup.py`:

1. **Байт-різні форми URL** (`www`/`?utm_`/trailing) з різним content_hash →
   один рядок, `last_seen_at` оновлено (не два pending).
2. **rejected-дубль**: перший rejected → другий (той самий article, дрейф content) →
   skip, лишається один rejected, нового pending нема.
3. **published-дубль**: перший published → другий → skip, `last_seen` bump, shadow НЕ
   створюється.
4. **Різні `article_url`** → два окремі офери (нема хибного злипання).
5. **Регрес source-bound**: офер із заданим `source_id` → гілки 2/3 працюють як раніше
   (нова гілка не перехоплює).
6. **blocked-дубль**: перший blocked→rejected, другий із дрейфом content_hash → skip по
   article (не INSERT новий rejected).

## Ризики

- **Хибне злипання різних оферів на одній сторінці-агрегаторі.** Пом'якшено: агрегатори
  вже мають окремий шлях (`aggregate_page` дає один офер зі списком знижок на сторінку),
  а host-blocklist агрегаторів фетч не пускає. Для звичайного бізнес-сайту одна
  промо-сторінка = один офер — саме те, що треба.
- **Втрата легітимної зміни на discovered published.** Прийнято: активний краулер лише
  skip; зміни на published — робота пасивного прогону. Компроміс погоджено.
