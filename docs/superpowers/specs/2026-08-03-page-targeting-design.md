# Якісний добір сторінок для DomainWalker — дизайн

Дата: 2026-08-03
Гілка: `feat/page-targeting`
Пам'ять: [[ubd-crawler-sitemap-depth]] (walker), [[ubd-crawler-marketing-lexicon-autofill]] (promo_lexicon), [[ubd-crawler-extractor-precision]] (discount-гейт)

## Проблема

`DomainWalker` обирає сторінки для фетчу/екстракції через **вузький** `promo_lexicon.url_is_promo(url)`
— матч лише промо-слагів у path (`sale/promo/акці/знижк/discount/offer/розпродаж/дисконт/вигід/
bonus/cashback/special/hot`). І sitemap-фільтр, і BFS-класифікація лінків обмежені цим.

Реальні дані: **більшість оферів УБД живуть на інфо-сторінках, які цей фільтр НЕ матчить** —
контакти, доставка/оплата, про нас, програма/бонусна програма лояльності, **сторінки «для
військових/ветеранів»** («Знижка для військовослужбовців»), «Корисна інформація», FAQ, головна.
Тобто walker **недобирає** ці сторінки. Водночас BFS-fallback (коли промо-сторінок <`bfs_trigger_min`)
фетчить до `bfs_max_pages` сторінок «наосліп» через нейтральні лінки — марнота на товарах/блозі.

Задача **двобічна** (обидва напрями, підтверджено): **(1) розширити** цільовий набір, щоб
включити високоврожайні інфо-сторінки; **(2) відсікти** низьковрожайне (товари/кошик/акаунт/
блог), — **без втрати якості** крола.

## Рішення (огляд)

Замінити вузький `url_is_promo` у walker на **таксономію цільових типів сторінок** із двома
сигналами (URL-слаг + текст лінка) і **пріоритетом відсіку**. Таксономія — **курована в коді**
(як наявний `url_is_promo`), **без config-ручки**.

## Класифікатор `page_is_target`

Новий класифікатор у `crawler/crawler/discovery/promo_lexicon.py` (поряд із `url_is_promo`):

```python
INCLUDE_TOKENS: tuple[str, ...] = (...)   # UA + translit слаги цільових типів
EXCLUDE_TOKENS: tuple[str, ...] = (...)   # низьковрожайні слаги
INCLUDE_ANCHORS: tuple[str, ...] = (...)  # сигнали в тексті лінка (UA фрази, lower)

def page_is_target(url: str, anchor_text: str | None = None) -> bool:
    path = unquote(urlsplit(url or "").path).lower()
    if any(t in path for t in EXCLUDE_TOKENS):
        return False                                    # відсік ПЕРЕМАГАЄ
    if any(t in path for t in INCLUDE_TOKENS):
        return True                                     # слаг URL
    if anchor_text and any(a in anchor_text.lower() for a in INCLUDE_ANCHORS):
        return True                                     # текст лінка (для непрозорих URL)
    return False
```

- **URL-слаг** — працює на sitemap (анкора нема) і в BFS.
- **Текст лінка** — ловить сторінки з непрозорими URL (`/page/12` з текстом «Знижка для
  військовослужбовців»); у BFS `<a>` вже парситься, тож сигнал дешевий.
- **EXCLUDE перемагає INCLUDE**: `/product/sale-shoes` (містить `sale` і `product`) → False,
  щоб не фетчити тисячі товарних сторінок, які випадково містять промо-слаг.
- Substring-матч по path (як наявний `url_is_promo`) — токени добирати обережно проти
  хибних збігів (тести це покривають).

## Таксономія (курована)

**INCLUDE типи** (обʼєднання токенів; промо-набір лишається як підмножина):
| Тип | Слаг-токени (додатково до наявних промо) | Анкор-сигнали |
|---|---|---|
| Головна | `/` (завжди додається у `_finalize`) | — |
| Акції/знижки | *(наявний `SEED_URL_TOKENS`)* | «акці», «знижк» |
| **Для військових/ветеранів** ⭐ | `viysk`, `viyskovosluzhb`, `military`, `army`, `veteran`, `zsu`, `zahisnik`, `defender`, `ubd` | «військов», «ветеран», «ЗСУ», «захисник», «УБД», «знижка для військовослужбовців» |
| Контакти | `kontakt`, `contact` | «контакти» |
| Доставка й оплата | `dostavka`, `oplata`, `delivery`, `payment`, `shipping` | «доставка», «оплата» |
| Про нас | `pro-nas`, `pro-kompaniyu`, `about`, `o-nas` | «про нас», «про компанію» |
| Лояльність / бонусна програма | `loyaln`, `loyalty`, `bonus`, `bonusna`, `club`, `klub` | «лояльність», «бонусна програма», «клуб» |
| FAQ | `faq`, `pytannya` | «питання», «відповіді» |
| **Корисна інформація** | `korysn`, `korisn`, `useful` | «корисна інформація» |

**EXCLUDE токени** (відсік — не фетчити, не у BFS-фронтир):
`/product`, `/tovar`, `/goods`, `/item`, `/p/`, `cart`, `koshyk`, `checkout`, `basket`,
`account`, `login`, `register`, `cabinet`, `kabinet`, `profile`, `wishlist`,
`blog`, `news`, `novyny`, `search`, `poshuk`, `filter`, `tag`, `privacy`, `cookie`.

Токени наведені орієнтовно; фінальний вивірений список — у плані (з тестами на хибні збіги,
напр. `army` vs «pharmacy», `/p/` vs «/help/»).

## Інтеграція у `walker.py`

- **sitemap-фільтр** (`walk`): `promo_filter=lambda u: _same_domain(u, domain) and page_is_target(u)`
  замість `url_is_promo`; той самий `page_is_target(u)` у наступному list-comprehension.
- **BFS** (`_bfs` + `_links`): `_links` повертає `list[tuple[str, str]]` = `(absolute_url, anchor_text)`.
  Для кожного лінка в `_bfs`:
  - `page_is_target(url)` з path-only коротко перевіряє EXCLUDE (path-EXCLUDE → повний skip: не збирати, не у фронтир — не лізти в товари/блог);
  - інакше `page_is_target(url, anchor)` → target → зібрати в `found`;
  - інакше нейтральне → у фронтир (`nxt`, йти глибше).
  (Реалізаційно: одна перевірка EXCLUDE окремо для skip, потім target для collect, інакше frontier.)
- `_finalize`, `page_cap`, per-domain politeness, homepage-always-first — **без змін**.
- `url_is_promo` **лишається** (промо = підмножина target; його наявні тести не чіпаємо).
  Walker більше його прямо не викликає, але re-export можна лишити для сумісності.

## Що НЕ змінюється / межі

- **Якість зберігається downstream**: `HeuristicExtractor(require_discount=True)` (продакшн-дефолт,
  [[ubd-crawler-extractor-precision]]) все одно віддає офер лише за конкретної знижки — розширення
  INCLUDE **не** заливає чергу сміттям; EXCLUDE прибирає лише сторінки, де знижок УБД майже не буває.
- `page_cap=10`, `sitemap_max_docs`, `bfs_max_*`, politeness-шар — незмінні.
- Атрибуція/harvester/фіди/config — не чіпаємо.
- **Свідомий компроміс**: `blog`/`news` — hard-EXCLUDE. Бізнес-сайтний блог зрідка тримає саме
  ве-знижку (вона на інфо-сторінках), а окремі пости — шум; discount-гейт захищає ті, що фетчимо.
  Якщо згодом виявиться недобір — тип легко перевести з EXCLUDE у «нейтральне» (traverse-through).

## План тестів (TDD)

**`test_page_types.py`** (новий):
- кожен INCLUDE-тип матчиться своїм слагом (військові/контакти/доставка/про-нас/лояльність/FAQ/корисна-інформація);
- анкор-матч: непрозорий URL + анкор «Знижка для військовослужбовців»/«Корисна інформація» → True;
- EXCLUDE перемагає: `/product/sale` → False; `/koshyk` → False;
- нейтральне (`/random/page`) → False;
- хибні збіги: `army` не матчить «pharmacy»; `/p/` не матчить «/help/»; тощо;
- промо-URL (наявна поведінка) досі target.

**`test_walker` / `test_promo_url_filter`** (доповнити/адаптувати):
- sitemap-фільтр використовує `page_is_target` (інфо-сторінка проходить, товарна — ні);
- BFS: `_links` повертає `(url, anchor)`; target-лінк (за анкором) збирається; excluded-лінк
  повністю пропускається (не у фронтир); нейтральний — у фронтир.

## Критерії готовності

- Нові + наявні crawler-тести зелені (`pytest -q`).
- Walker таргетить інфо-типи (контакти/доставка/про-нас/лояльність/військові/FAQ/корисна-інформація)
  за слагом і за текстом лінка; відсікає товари/кошик/акаунт/блог.
- `url_is_promo` та його тести не зламані.
- Жива Docker-перевірка: на реальному домені walker повертає інфо-цільові URL, не товарні.
