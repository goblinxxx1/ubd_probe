# FIXED-гілка екстрактора: гейт знижкового контексту

Дата: 2026-08-05
Трек: Трек 1 (точність екстрактора — остання незагейтована discount-гілка)
Гілка: `track-fixed-context`

## Проблема

У `crawler/crawler/extract/heuristic.py` три discount-гілки емітять `discount_type`:

```python
if pl.FREE.search(low) and _has_audience_in_text(text):        # free — гейт аудиторії-в-блоці (#35)
    discount_type = "free"
elif (m := _PERCENT.search(text)) and pl.DISCOUNT_CTX.search(low):   # percent — гейт DISCOUNT_CTX
    discount_type, discount_value = "percent", m.group(1)
elif (m := _FIXED.search(text)):                               # fixed — БЕЗ жодного гейту
    discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))
```

`_FIXED = (\d[\d\s]{0,7})\s*(?:грн|гривень|₴|uah)` матчить **будь-яку суму в гривнях**. Тож голу
**ціну** («Куртка 2000 грн»), суму пожертви («внесок 1000 грн»), «від 1000 грн» тощо екстрактор
класифікує як fixed-**знижку** — хоча знижки там немає. Це остання структурна асиметрія: PERCENT
вимагає `DISCOUNT_CTX`, FREE вимагає аудиторію-в-блоці, а FIXED — нічого.

Наслідок: сторінки з offer-тригером, що **не** є знижковим контекстом (`тільки сьогодні`, `бонус`,
`уцінк`, `ліквідац`, `супер ціна`, `діє до`…) + голою ціною + аудиторією просочуються в чергу як
хибні fixed-офери. (Аудиторія вже гейтується глобально на `heuristic.py:123` — тож проблема суто
«ціна ≠ знижка».)

## Рішення

Додати `and pl.DISCOUNT_CTX.search(low)` до FIXED-гілки — **дзеркалить PERCENT**:

```python
    elif (m := _FIXED.search(text)) and pl.DISCOUNT_CTX.search(low):
        discount_type, discount_value = "fixed", re.sub(r"\s", "", m.group(1))
```

`DISCOUNT_CTX = знижк|акці|розпродаж|спецпропоз|промокод|економ|вигід|-\s*\d`. Тобто сума=знижка
лише за наявності явного знижкового контексту (`знижка 500 грн`, `-500 грн`, `економія 1000 грн`,
`розпродаж … 500 грн`). Гола ціна/пожертва без контексту → не fixed.

### Семантика (дзеркалить #35)

Гейт міняє **класифікацію знижки**, а не лише відсів:
- **prod** (`require_discount=True`, дефолт через wiring): fixed-без-контексту → `discount_type=None`
  → `heuristic.py:106` `return None`, офер відсіюється.
- **permissive** (class-default `require_discount=False`): офер **не** відсівається, але тепер
  емітиться **без** (хибної) fixed-знижки (`discount_type=None`, `discounts=[]`).

**Permissive НЕ byte-eq** до pre-track — свідомо, точно як #35 для FREE: precision-гейт корегує
класифікацію в обох режимах, а `require_discount` керує лише відсівом. (До #30/#35 «permissive =
byte-eq» вже було ослаблене FREE-гейтом.)

### Churn-guard

`content_hash` рахується з `(promo_title, provider, text)` (`heuristic.py:145`), **не зі знижки** —
зміна гейту не пере-хешує наявні офери. Та сама логіка, що в #35.

### Симетрія завершена

free (аудиторія-в-блоці) / percent (DISCOUNT_CTX) / fixed (DISCOUNT_CTX) — усі три гілки
контекстно-гейтовані. Екстрактор стає цілісним.

## Свідомі компроміси (YAGNI / межі скоупу)

- **бонус/кешбек fixed-суми відсіюються.** `бонус`/`кешбек` — offer-тригери, але не в DISCOUNT_CTX.
  «Бонус 1000 грн» без знижкового контексту → відсіється. Прийнято: неоднозначні value-back суми
  без явного знижкового контексту — радше шум; free/percent-гілки з цими тригерами працюють як
  раніше. Розширення DISCOUNT_CTX словами `бонус|кешбек` — окреме лексиконне рішення, поза скоупом
  (це deferred Minor з #30).
- **Page-level DISCOUNT_CTX (не block-level).** Дзеркалимо PERCENT (той самий рівень точності), не
  FREE (block-level). Якщо page-level виявиться заслабким (як свого часу FREE) — block-level pass
  окремим треком. Не over-engineer-имо зараз.
- `_FIXED` regex не чіпаємо (breadth ок під гейтом).

## Тести (TDD, `crawler/tests/test_heuristic.py`)

Хелпери файлу: `CATS`/`_item(text)`/`get_extractor("heuristic")`/`HeuristicExtractor(require_discount=)`.

1. **fixed + контекст → емітиться** (регрес-guard): `HeuristicExtractor(require_discount=True)` на
   «Знижка 500 грн для ветеранів» → `discount_type=="fixed"`, `discount_value=="500"`. (Наявні
   `test_extractor_hryven_full_form_gives_fixed` / `test_round_hryvnia_price_not_misread_as_free`
   уже мають «Знижка …» → лишаються зеленими, підтверджують відсутність регресу.)
2. **`-500 грн` стиль → емітиться**: «Розпродаж -500 грн для військових» (DISCOUNT_CTX через
   `розпродаж` і `-\d`; `_FIXED` матчить «500 грн») → `fixed`, `500`.
3. **fixed + аудиторія, БЕЗ контексту → None** (prod): `require_discount=True` на «Тільки сьогодні!
   Куртка 2000 грн для ветеранів» (тригер `тільки сьогодні`, ціна 2000 грн, аудиторія, **немає**
   DISCOUNT_CTX) → `extract(...) is None`.
4. **permissive: не відсів, але без хибної знижки**: `HeuristicExtractor()` (default) на тому ж
   item з (3) → результат `is not None`, але `discount_type is None` (ціна більше не читається як
   fixed-знижка).
5. **percent/free незмінні** (регрес): наявні `test_percent_discount_parsed` /
   `test_free_offer_parsed` лишаються зеленими (не чіпаємо ці гілки).

## Ризики

- **Легітимна fixed-знижка, сформульована без DISCOUNT_CTX-слова.** Напр. «Мінус 500 гривень
  ветеранам» — «Мінус» словом, не символом. DISCOUNT_CTX ловить `-\d` (символ), не слово «мінус».
  Пом'якшено: більшість fixed-знижок мають знижк/акці/розпродаж/-число; рідкісні словесні форми —
  прийнятна втрата заради точності (та сама межа, що в PERCENT). Розширення лексикону — окремо.
- Малий blast-radius: одна умова в одній гілці; percent/free/require_discount/audience-gate
  недоторкані.
