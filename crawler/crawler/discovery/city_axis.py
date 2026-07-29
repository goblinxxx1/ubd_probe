"""City query axis: suffix a rotating Ukrainian city onto base search phrases.

City is an INDEPENDENT rotating axis (its own cursor), NOT a cartesian product
with the {intent}{audience} grid — one city per pass is appended to a slice of
the current phrase batch, so the (city × phrase) space is swept diagonally over
passes without materialising it. Reuses the shared gazetteer (cities + смт);
the canonical name is the query suffix (inflected forms are for extraction)."""

from crawler.discovery import geo


def _load_city_names(entries=None) -> list[str]:
    entries = geo._load_entries() if entries is None else entries
    seen: set[str] = set()
    out: list[str] = []
    for e in entries:
        name = (e.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


class CityAxis:
    """Deterministic rotation over city names; suffixes the current city onto a
    slice of base phrases. One city advance per pass (caller drives the cursor)."""

    def __init__(self, cities: list[str] | None = None):
        self._cities = list(cities) if cities is not None else _load_city_names()

    def __len__(self) -> int:
        return len(self._cities)

    def next_batch(self, base_phrases: list[str], cursor: int, k: int
                   ) -> tuple[list[str], int]:
        size = len(self._cities)
        if size == 0 or k <= 0:
            return [], cursor
        cursor %= size                              # normalises negative / out-of-range
        city = self._cities[cursor]
        out = [f"{p} {city}".strip() for p in base_phrases[:k] if p and p.strip()]
        return out, (cursor + 1) % size
