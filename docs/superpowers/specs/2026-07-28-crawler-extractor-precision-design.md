# Точність екстрактора: discount-gate + розширення детекції

**Дата:** 2026-07-28
**Гілка:** `feat/crawler-extractor-precision`
**Скоуп:** crawler-only (екстрактор + лексикон + config + wiring). Backend/admin не чіпаємо.

## Проблема

Черга модерації заливається сміттям: із 27 pending-оферів живого стека **18 не мають знижки** (`discount_type IS NULL`) — це не офери, а фрагменти сторінок, які евристичний екстрактор над-екстрактить:
- нав-меню («Клієнтам Про Нас Про автора»),
- проза («Періоди розпродажів завжди актуальні для українців»),
- пункти умов («1.», «2.», «3.», «*Знижки надаються в присутності військовослужбовця»),
- інстаграм-заклики («вподобати публікацію про акцію»).

**Корінь:** `heuristic.py HeuristicExtractor.extract` (рядки 57–109) емітить `OfferCandidate` за наявності trigger-слова (`pl.offer_triggers()`, напр. «знижк»/«розпродаж») + збігу target-лексикону, **навіть коли `discount_type is None`** (немає жодного конкретного `%`/`грн`/free-сигналу). Прозовий текст про знижки без числа проходить.

*(NB: це давня проблема якості екстрактора, не регрес треку пасивної ре-модерації — той коректно бампає published-офери, не заводить їх у чергу повторно.)*

Дані-докази: 7 pending **з** знижкою — усі легітимні («Знижка 20% для ветеранів у кафе», «Знижки для МВС/НАБУ/ДСНС», «Офтальмологія…до 15%»); 18 **без** знижки — усі сміття. Гейт «є конкретна знижка» відсікає рівно 18, лишає 7.

## Рішення

Crawler-only, дві частини + ретро-очищення. Прапор `require_discount` (config-дефолт **True**) вмикає гейт; OFF = поточна поведінка (byte-eq rollback), за конвенцією проєкту [[feedback-preserve-working-structure]].

### Компонент A — розширення FREE-детекції (`crawler/discovery/promo_lexicon.py`)

Раз гейт жорсткий, детекція знижки стає воротарем — розширюємо `FREE`, щоб не втратити реальні free/подарунок-офери. Поточне: `безкоштов|безплатн|\bfree\b`. Нове (додати, курований набір):

```python
FREE = re.compile(
    r"безкоштов|безплатн|безоплатн|\bfree\b|"
    r"[ву]\s+подарунок|у\s+дарунок|"      # кваліфіковані форми; голе "подарунок" над-матчить ("купіть подарунок")
    r"даром|задарма|0\s*(?:грн|₴)",
    re.IGNORECASE)
```

Дрібно: `_FIXED` у `heuristic.py` додає повну форму `гривень` поряд із `грн|₴|uah`:
```python
_FIXED = re.compile(r"(\d[\d\s]{0,7})\s*(?:грн|гривень|₴|uah)", re.IGNORECASE)
```

**Безумовно** (покращення детекції, не за прапором): `content_hash` рахується з `(title, provider, text)`, не зі знижки → ключі дедупу/мерджу незмінні; при `require_discount=False` множина емітованих оферів та сама, лише деякі отримують `discount_type=free` замість `None` (payload-поле, не дедуп-ключ).

### Компонент B — discount-гейт (`heuristic.py` + `extract/base.py` + `config.py` + `wiring.py`)

- **`heuristic.py`:** `HeuristicExtractor.__init__(self, require_discount: bool = False)` (permissive class-default — щоб наявні прямі `HeuristicExtractor()` у тестах лишались зеленими); зберігає `self._require_discount`. У `extract`, одразу після блоку обчислення `discount_type` (після рядка ~69, перед `valid_until`):
  ```python
  if self._require_discount and discount_type is None:
      return None
  ```
- **`extract/base.py`:** `get_extractor(name: str, require_discount: bool = False)` → `HeuristicExtractor(require_discount=require_discount)`.
- **`config.py`:** додати `require_discount: bool = True` у трьох місцях (дзеркало `domain_rating_enabled`): поле env-Settings, поле CrawlConfig, builder-передача. Config-дефолт **True** = гейт увімкнений у продакшні.
- **`wiring.py`:** рядок 106 `extractor = get_extractor(config.extractor, require_discount=config.require_discount)`.

Гейт діє однаково для passive deep-walk (`runner._process_item`) і active-harvest (`harvest._process_page`, спільний екстрактор) — обидва більше не емітять офери без знижки.

### Ретро-очищення живої черги (post-deploy ops, не код)

Після ребілду краулер-образу — прибрати наявні сміттєві pending із живої БД `ubd_probe-db-1`. Ціль: `status='pending_review' AND type='discount' AND discount_type IS NULL`. Порядок як у попередньому очищенні черги (child-first через FK): спершу `offer_links`/`offer_offer_categories`/`offer_target_categories` за `offer_id IN (<ціль>)`, тоді самі `offers`. Краулер їх більше не відтворить (гейт). Published/rejected не чіпаємо. Точні команди — у плані.

## Тести

- **Наявні** (`test_heuristic.py` та ін., що будують `HeuristicExtractor()` без аргументу) — permissive class-default → зелені без змін.
- **Нові (`test_heuristic.py`):** (1) `require_discount=True` + текст без знижки → `None`; (2) `require_discount=True` + текст із `%`/`грн`/free-синонімом → офер; (3) кожен новий FREE-синонім (`безоплатн`, `подарунок`, `0 грн`, `даром`) → `discount_type="free"`; (4) `гривень` → `fixed`; (5) `require_discount=False` (default) + без знижки → офер (byte-eq rollback).
- **`test_config.py`:** `require_discount` дефолт True + env-override.
- **`test_wiring.py`:** wired-екстрактор дістає `require_discount=True` з конфіга (напр. `extractor._require_discount is True`).

Crawler baseline 420 має лишитися зеленим + нові зверху.

## Не-скоуп (YAGNI)

- **Сегментація сторінки на RawItem-и** (джерело фрагментів «1.»/«2.») — глибший окремий трек; discount-гейт уже прибирає більшість.
- **Тайтл-якість / нав-фільтри / відсів маркетинг-прози** (Варіант 2 брейнштормінгу) — не тепер; обрано чистий discount-гейт (Варіант 1).
- Backend/admin/схема — без змін.
