"""Offline curated query grid: generate DDG search phrases from vocabulary axes.

v1 templates only: "{intent} {audience}" and "{brand} {audience}". Cities are
NOT a query axis (they live in geo.py for extraction). Deterministic, stable
order — the same technique as lexicon.py/geo.py: curated tuples, no ML."""

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


def build_grid() -> list[str]:
    """All "{intent} {audience}" then all "{brand} {audience}", deduped, stable order."""
    seen: set[str] = set()
    out: list[str] = []
    for head in (*INTENT_FORMS, *BRANDS):
        for aud in AUDIENCE_FORMS:
            q = f"{head} {aud}".strip()
            key = q.casefold()
            if q and key not in seen:
                seen.add(key)
                out.append(q)
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
