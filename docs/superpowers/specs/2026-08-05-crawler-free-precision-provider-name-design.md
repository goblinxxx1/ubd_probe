# Extractor: free-proximity gate + provider = company/site name

**Дата:** 2026-08-05
**Гілка:** `feat/crawler-free-precision-provider-name` (від `main`)
**Тип:** crawler-only (екстрактор). Backend/admin/public не змінюються.

## Мотивація

1. **Хибний `free`** — найбільший залишковий шум черги після хост-гейту (трек #34). У
   `heuristic.py` `percent` вимагає `DISCOUNT_CTX` поруч (рядок 95), а **`FREE` не вимагає
   жодного контексту** (рядок 93): будь-яке «безкоштовно» на generic-сторінці («Умови доставки»,
   «Про команду», «Контакти») + аудиторія будь-де в `blob = provider+site_name+text` (рядок 116) →
   free-офер. Аудиторія там часто збігається лише з **назвою провайдера**, не з прозою блока.
2. **«Хто пропонує знижку»** зараз показує голий домен (`uglovoy.com.ua`), а треба **назву
   компанії/сайту** («Гастро-бар Угловой»). Фетчер уже витягує `item.site_name`
   (`_extract_site_name`: og:site_name → title → h1).

## Ключові факти з коду

- `website.py` дробить сторінку поблочно (`tree.css("article, li, p")`, зовнішній блок) — **кожен
  блок = окремий RawItem**; `item.text` ≈ один абзац/блок. Отже «free + аудиторія в тексті того
  самого `item.text`» = «в одному абзаці» (вибір користувача).
- `extract(item, provider, categories)`: `provider` = `attr.provider` (атрибуйований **хост**).
  `OfferCandidate.provider = provider` (рядок 131); `content_hash(promo_title, provider, text)`
  (рядок 138) — теж хост.

## Дизайн

### Компонент 1 — free-proximity gate (в межах блока)
`free` зараховується лише коли free-тригер **І** термін-аудиторія присутні **в тексті того самого
блока** (`item.text`), а не лише в метаданих:
```python
if pl.FREE.search(low) and _has_audience_in_text(text):
    discount_type = "free"
elif (m := _PERCENT.search(text)) and pl.DISCOUNT_CTX.search(low):
    ...
```
де `_has_audience_in_text(text)` = `bool(classify(text, TARGET_LEXICON))` (аудиторія в
**прозі блока**, НЕ в `provider`/`site_name`). Якщо free не проходить — падає в `elif` (percent/fixed),
тож сторінка з реальним «-20% ветеранам» + generic «безкоштовно» лишиться як percent.
Загальний аудиторія-гейт офера (рядок 116-118, по blob) — **незмінний**; це додаткова перевірка
саме для валідності `free`.
- Реальний «Безкоштовні протези **ветеранам**» — аудиторія в тексті → проходить.
- Generic «безкоштовна доставка» на «Умови доставки», аудиторія лише з назви бренду → відсів.
- Компроміс: сторінки, де промо — один великий `<article>` (багато абзаців в блоці), гранулярніші
  не стають; новинний підклас уже ловить хост-гейт (#34).

### Компонент 2 — provider = назва компанії/сайту
`OfferCandidate.provider` = **`item.site_name`** (назва), з фолбеком на хост:
```python
display_provider = (item.site_name or "").strip() or provider
# OfferCandidate(provider=display_provider, ...)
```
**Churn-guard:** `content_hash` і `blob` (класифікація) **лишаються на хості** (`provider`-параметрі)
— наявні офери НЕ пере-хешуються; класифікація не змінюється (`site_name` і так у blob).

**Взаємодія з бекенд-гейтом (#34):** гейт `_blocked_source_host` перевіряє bare-host
`provider`/`site_url`/`article_url`. Після зміни `provider` на назву (без крапки) provider-гілка
гейту стає інертною для таких оферів, АЛЕ `site_url`/`article_url`-перевірки лишаються (реальні
хости). Соц-junk (google.com/linkedin.com як колишній provider) все одно ловляться через
site/article-хост. Регресії гейту немає для основного класу; зафіксовано як відомий компроміс.

## Поза скоупом (свідомо)
`fixed` (рядок 97 теж без контексту — окремо, менший шум); дублікати; charity/generic без будь-якої
знижки, де немає free-тригера; додавання `target_url` у бекенд-гейт (окремо, backend).

## Тести (crawler pytest)
- free + аудиторія в тексті блока → free-офер (проходить);
- free БЕЗ аудиторії в тексті (аудиторія лише в provider/site_name) → free відкинуто → офер None
  (require_discount) АБО percent, якщо є `-N% + DISCOUNT_CTX`;
- free відкинуто, але percent з контекстом присутній → офер percent (елиф-фолбек);
- provider = item.site_name коли є; фолбек на хост коли site_name порожній;
- content_hash НЕ змінюється при зміні display-provider (churn-guard: хеш на хості);
- регресія: наявні published-подібні кейси (free біля аудиторії) лишаються оферами.
