# Приборкати walk мегамаркетів: BFS-каталог-скіп + активний empty-pass-skip

**Дата:** 2026-08-25
**Гілка:** `fix/crawler-tame-megamart-walk`

## Проблема (root cause, доведено)

Краулер фетчить генеричні каталог-сторінки мегамаркетів (напр.
`https://epicentrk.ua/ua/shop/razdvizhnye-sistemy-dlya-dverey/`). Діагностика:

1. **BFS обходить нейтральні каталог-категорії.** `DomainWalker._bfs` ([walker.py:104-128])
   фетчить кожну сторінку фронтиру, щоб дістати лінки. Лінк, що ні `page_is_target`,
   ні `is_excluded` — «нейтральний» → додається у `nxt` і **обходиться глибше**
   ([walker.py:126]). `/shop/<категорія>/` нейтральні (`EXCLUDE_TOKENS` блокує лише
   `/product`,`/tovar`,`/goods`,`/item`,`/p/` — сторінки ТОВАРУ, не каталог-категорії),
   тож на мегамаркеті BFS-бюджет (`bfs_max_pages=8`) витрачається на генеричні категорії, ~0 користі.
2. **Активний harvest не поважає empty-pass-skip.** `record` ([domain_registry.py:67-69])
   озброює `skip_left=5` на 0-оферному проході, але `take_skip` споживається лише в
   **passive**-шляху ([runner.py:332]). Активний harvest (яким і йде epicentrk через
   brand/osm/registry-фіди) `take_skip` не викликає → skip нескінченно оминається;
   мегамаркет walk'иться щопрохід попри 0 користі.

## Рішення

Крауле-only. Два незалежні фікси.

### Фікс #1 — BFS не обходить генеричні каталог-категорії

`crawler/crawler/discovery/promo_lexicon.py` — новий набір + гелпер:
```python
# Генеричні каталог/категорійні сторінки: у BFS їх НЕ обходимо (не фетчимо глибше) —
# на мегамаркеті вони палять BFS-бюджет без користі. Окремо від EXCLUDE_TOKENS: EXCLUDE
# виграв би над page_is_target і вбив би промо під каталогом (напр. /shop/akcii/).
NO_TRAVERSE_TOKENS: tuple[str, ...] = (
    "/shop/", "/catalog", "/category", "/collection", "/brands", "/c/",
)

def is_catalog_page(url: str) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    return any(t in path for t in NO_TRAVERSE_TOKENS)
```

`crawler/crawler/discovery/walker.py` — у `_bfs`, між target-перевіркою і traverse:
```python
if is_excluded(link) or is_ru_by_geo(link):
    continue
if page_is_target(link, anchor):
    found.append(link)                 # промо/ветеран виграє навіть під /shop/ (напр. /shop/akcii/)
elif is_catalog_page(link):
    continue                            # генерична каталог-категорія → НЕ обходити
else:
    nxt.append(link)                    # інша нейтраль → обхід деп.
```
Імпорт `is_catalog_page` додати до наявного `from crawler.discovery.promo_lexicon import (...)`.

**Порядок критичний:** `page_is_target` ПЕРЕД `is_catalog_page`, щоб `/shop/akcii/`
(page_is_target=True через `akci`) збирався, а не скіпався. Компроміс (свідомий):
офер, схований суто під `/shop/cat/deeper/` без промо/ветеран-слага, не дістанемо —
але такі офери зазвичай на промо/ветеран-слагах, які target ловить прямо з сайтмепу/homepage.

### Фікс #2 — активний harvest поважає empty-pass-skip

`crawler/crawler/discovery/harvest.py` — у `_select_fetch_set` (фаза-1, серійна, поруч
з наявними website skip-гейтами), після обчислення `host` (~ряд 142):
```python
if (cand.type == "website" and self._registry is not None
        and self._registry.take_skip(host)):
    continue                            # empty-pass cooldown: скіп walk цього домену
```
Гейт на рівні harvest → б'є ВСІ фіди (brand/osm/registry), не лише registry. `take_skip`
споживає один skip (side-effect, як `geo_block.add` вище). Домен зі `skip_left>0` не
займає бюджет-слот; `skip_left==0` — фетчиться, і `record` після 0-оферного проходу
переозброює. Ефект: epicentrk walk'иться ~1 із 6 проходів. Консистентно з passive
([runner.py:332]).

Примітка: passive+active можуть обидва викликати `take_skip` для того ж хоста (подвійне
споживання) — прийнятно (feed-домени й passive-джерела здебільшого не перетинаються;
у гіршому разі skip швидше вигорає). Не ускладнюємо.

## Тести (TDD)

- `test_promo_lexicon.py`: `is_catalog_page` True на `/ua/shop/razdvizhnye-.../`,
  `/catalog/...`, `/category/...`; False на `/ua/actions/`, `/veteranam/`, `/shop/akcii/`
  (останнє — бо це task target-перевірки; сам `is_catalog_page` на `/shop/akcii/` = True,
  тож тестуємо саме що BFS-логіка target'ить його — див. walker-тест).
- `test_walker.py` (BFS): нейтральна `/shop/cat/` НЕ у traverse-фронтирі й не фетчиться
  глибше; промо `/shop/akcii/` (target) — збирається; проста нейтраль (`/pro-shop-news/`
  без каталог-токена) — обходиться. Через fake-client із контрольованими лінками.
- `test_active_harvest.py`: website-кандидат зі `skip_left>0` (armed через registry.record
  0 offers) пропускається у `_select_fetch_set` (не в selected, бюджет не витрачено);
  `skip_left==0` — у selected.
- Наявні walker/harvest/promo тести лишаються зелені.

## Жива валідація

Після фіксу + ребілд: у наступних логах краулера немає нових `GET …/shop/<cat>/`
для мегамаркета; epicentrk у логах рідше (skip між проходами).

## Поза скоупом (свідомо)

- Не блокуємо мегамаркети цілком (вони мають легіт-промо `/vygoda/`,`/actions/`).
- Англо-промо-слаги (`action`/`sale`/`deal`) як target — окремий трек (варіант #3 з
  розслідування; `sale`/`deal` раніше свідомо прибирали як over-match).
- Backend/admin/міграції.
