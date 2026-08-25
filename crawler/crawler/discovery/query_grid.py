"""Offline curated query grid: generate DDG search phrases from vocabulary axes.

build_grid materializes "{intent} {audience}" (the 351 base) plus a geo block
"{intent} {audience} {city}" over a curated top-city list (GRID_CITIES) — city
is a TRUE grid multiplier (B3a), not the old diagonal suffix. Brands are not a
query axis — brand DOMAINS are covered directly by brand_feed. geo.py still
recognizes the full gazetteer for EXTRACTION; only query targeting is curated.
Deterministic, stable order — curated tuples, no ML."""

# Audience surface forms (map onto the 7 canonical TARGET_LEXICON slugs).
AUDIENCE_FORMS = (
    "військові", "військовослужбовці", "військові ЗСУ", "ЗСУ", "чинні військові",
    "мобілізовані", "контрактники", "резервісти", "ветерани", "ветеран",
    "ветеран війни", "ветерани АТО", "ветерани ООС", "УБД", "учасники бойових дій",
    "особи з інвалідністю внаслідок війни", "родини військових", "дружини військових",
    "діти військових", "сім'ї УБД", "сім'ї загиблих Захисників", "члени сімей полеглих",
    "поліцейські", "ДСНС", "прикордонники", "ТРО", "Нацгвардія",
)

# Concrete discount-type surface forms (gov/NGO-noise program terms excluded).
INTENT_FORMS = (
    "знижка", "безкоштовно", "акція", "спеціальна пропозиція", "бонус", "подарунок",
    "кешбек", "промокод", "сертифікат", "компенсація", "ваучер",
    "спеціальна ціна", "пільгова ціна",
)

# Curated top cities as a TRUE grid multiplier (B3a). ~45 largest / oblast
# centres, government-controlled — occupied cities excluded (no live merchant
# offers). Small towns stay in geo.py for EXTRACTION; only query targeting narrows.
GRID_CITIES = (
    "Київ", "Харків", "Одеса", "Дніпро", "Львів", "Запоріжжя", "Вінниця",
    "Полтава", "Чернігів", "Черкаси", "Житомир", "Суми", "Хмельницький",
    "Чернівці", "Рівне", "Тернопіль", "Івано-Франківськ", "Луцьк", "Ужгород",
    "Кропивницький", "Миколаїв", "Херсон",
    "Кривий Ріг", "Кременчук", "Біла Церква", "Кам'янське", "Умань", "Бровари",
    "Бориспіль", "Ірпінь", "Буча", "Нікополь", "Павлоград", "Олександрія",
    "Ковель", "Калуш", "Дрогобич", "Червоноград", "Мукачево", "Бердичів",
    "Ніжин", "Конотоп", "Шостка", "Ізмаїл", "Краматорськ",
)  # 45

# Curated geo-slice: only these strong intent/audience forms get a city suffix,
# keeping the materialized space ~1701 (30 geo-base × 45 cities = 1350 + 351).
GEO_INTENTS = ("знижка", "акція", "безкоштовно", "спеціальна пропозиція",
               "пільгова ціна")
GEO_AUDIENCES = ("військові", "ветерани", "УБД", "учасники бойових дій",
                 "ветеран війни", "мобілізовані")

# Service-block axes (B3b + A): a concrete service crossed with a discount modifier
# and a core audience. The modifier is folded into the EXISTING per-service budget —
# 2 modifiers × 3 audiences = 6 phrases/service, the same count as the old 6-audience
# 2-token block — so the grid does NOT grow, but each phrase now biases DDG toward
# pages that actually carry a discount (precision at the search stage, upstream of
# the extractor). The long-tail audiences stay covered by the base 351 grid.
SERVICE_MODIFIERS = ("знижка", "безкоштовно")
SERVICE_AUDIENCES = ("військовим", "ветеранам", "УБД")

# Curated cold-start service seed: concrete commercial services where a veteran
# discount is TYPICAL, so they're worth searching before the miner has offers to
# learn from. Excludes brands (→ BRANDS/brand_feed axis) and gov/NGO-program terms
# (credit/mortgage/utilities — the same noise the extractor gates fight). Uncertain
# categories (e.g. legal) are intentionally left to the miner to discover from real
# approved offers. Injected as always-in seed, never crowded out by the miner cap.
SEED_SERVICES = (
    # медицина / реабілітація
    "протезування зубів", "імплантація", "окуляри", "контактні лінзи",
    "МРТ", "УЗД", "фізіотерапія", "масаж спини",
    # відпочинок / оздоровлення
    "санаторій", "путівка", "СПА", "дитячий табір",
    # авто / СТО
    "СТО", "шиномонтаж", "заміна масла", "автомийка",
    "автоцивілка", "ОСЦПВ", "КАСКО", "пальне",
    # харчування (свідомо мало — категорія шумна)
    "кафе", "ресторан",
    # освіта
    "автошкола", "курси англійської", "підготовка до НМТ",
    # будівництво / техніка
    "металопластикові вікна", "меблі", "генератори", "побутова техніка",
    # побут / краса
    "барбершоп", "салон краси", "манікюр", "хімчистка", "ремонт взуття",
    # культура / спорт
    "музей", "театр", "кінотеатр", "спортзал", "басейн",
    # цифрові (бренди виключено)
    "домашній інтернет",
)

# Brand names (retail / fuel / pharmacy / tech / clothing / banks / post / telecom).
BRANDS = (
    "Rozetka", "Comfy", "Фокстрот", "Епіцентр", "Нова Лінія", "JYSK", "EVA", "Prostor",
    "Аврора", "Копійочка", "Сільпо", "АТБ", "Novus", "VARUS", "Metro",
    "OKKO", "WOG", "UPG", "SOCAR", "БРСМ", "KLO", "Parallel",
    "Подорожник", "АНЦ", "Бажаємо здоров'я", "Аптека Доброго Дня",
    "Алло", "Цитрус", "MOYO", "Brain", "Eldorado",
    "INTERTOP", "Colin's", "LC Waikiki", "Adidas", "Puma", "New Balance", "Megasport",
    "ПриватБанк", "monobank", "Ощадбанк", "ПУМБ", "Sense Bank", "Райффайзен Банк",
    "Нова пошта", "Київстар", "Vodafone", "lifecell",
)


def build_grid(cities: list[str] | None = None,
               services: list[str] | None = None) -> list[str]:
    """351 base + geo block (B3a) + service block (B3b: "{service} {audience}" over
    GEO_AUDIENCES). Base+geo order unchanged (byte-stable 1701 prefix); services
    appended after. `cities=[]`→no geo; `services` None/[]→no service block (byte-eq)."""
    city_list = list(GRID_CITIES) if cities is None else list(cities)
    svc_list = list(services or ())
    seen: set[str] = set()
    out: list[str] = []

    def _add(q: str) -> None:
        key = q.casefold()
        if q and key not in seen:
            seen.add(key)
            out.append(q)

    for head in INTENT_FORMS:                # base 351 — order unchanged
        for aud in AUDIENCE_FORMS:
            _add(f"{head} {aud}".strip())
    for head in GEO_INTENTS:                 # geo block: intent → audience → city
        for aud in GEO_AUDIENCES:
            for city in city_list:
                _add(f"{head} {aud} {city}".strip())
    for svc in svc_list:                     # service block (B3b+A): svc → modifier → audience
        for mod in SERVICE_MODIFIERS:
            for aud in SERVICE_AUDIENCES:
                _add(f"{svc} {mod} {aud}".strip())
    for svc in svc_list:                     # A2: гола вісь svc → audience (recall lever)
        for aud in SERVICE_AUDIENCES:        # без модифікатора: «автомийка військовим»
            _add(f"{svc} {aud}".strip())
    return out


def merge_queries(primary: list[str], extra: list[str]) -> list[str]:
    """Union preserving order, `primary` first, deduped case-insensitively."""
    seen: set[str] = set()
    out: list[str] = []
    for q in (*primary, *extra):
        key = (q or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out


class QueryGrid:
    """Deterministic rotation over the generated grid via an integer cursor."""

    def __init__(self, queries: list[str] | None = None):
        self._grid = queries if queries is not None else build_grid()

    def __len__(self) -> int:
        return len(self._grid)

    def next_batch(self, n: int, cursor: int) -> tuple[list[str], int]:
        size = len(self._grid)
        if size == 0:
            return [], 0
        n = max(1, min(int(n), size))
        if cursor < 0 or cursor >= size:
            cursor = 0
        batch = [self._grid[(cursor + i) % size] for i in range(n)]
        return batch, (cursor + n) % size

    def at(self, index: int) -> str:
        size = len(self._grid)
        if size == 0:
            return ""
        return self._grid[index % size]
