"""Gazetteer matcher: map Ukrainian city surface forms (incl. transliteration and
inflected cases, generated in crawler/scripts/build_gazetteer.py) to canonical names.

Precision guard: forms colliding with common Ukrainian words are flagged marker-only
(m=1) at build time and match only after a locality marker (м./с./смт/місто);
permissive forms (m=0) match anywhere. Token matching gives word boundaries for free
and supports multi-word names."""

import json
import re
from pathlib import Path

_MARKERS = {"м", "с", "смт", "місто", "селище"}
_TOKEN = re.compile(r"[a-zа-яїієґ'’\-]+", re.IGNORECASE)
_DATA_PATH = Path(__file__).with_name("gazetteer.json")


def _load_entries(path: Path = _DATA_PATH) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return []


def build_lookup(entries: list[dict]):
    """form(lower) -> (canonical, marker_only, nwords); returns (lookup, max_words)."""
    lookup: dict[str, tuple[str, bool, int]] = {}
    maxn = 1
    for e in entries:
        canon = e["name"]
        for form in e["forms"]:
            f = form["f"].lower()
            if not f:
                continue
            n = len(f.split())
            maxn = max(maxn, n)
            lookup.setdefault(f, (canon, bool(form["m"]), n))
    return lookup, maxn


_LOOKUP, _MAXN = build_lookup(_load_entries())


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower().strip("’'") for m in _TOKEN.finditer(text)]


def find_cities(text: str | None, lookup=None, maxn: int | None = None) -> list[str]:
    if not text:
        return []
    lookup = _LOOKUP if lookup is None else lookup
    maxn = _MAXN if maxn is None else maxn
    toks = _tokenize(text)
    found: list[str] = []
    seen: set[str] = set()
    i, n = 0, len(toks)
    while i < n:
        matched = False
        for w in range(min(maxn, n - i), 0, -1):
            hit = lookup.get(" ".join(toks[i:i + w]))
            if hit is None:
                continue
            canon, marker_only, _ = hit
            if marker_only:
                prev = toks[i - 1].rstrip(".") if i > 0 else ""
                if prev not in _MARKERS:
                    continue
            if canon not in seen:
                seen.add(canon)
                found.append(canon)
            i += w
            matched = True
            break
        if not matched:
            i += 1
    return found


def find_city(text: str | None, *_ignore) -> str | None:
    cities = find_cities(text)
    return cities[0] if cities else None


_ONLINE = re.compile(r"(?<!\w)(онлайн|інтернет[-\s]?магазин)\w*", re.IGNORECASE)


def is_online(text: str | None) -> bool:
    """Online-only signal — used as a location fallback when no city is found."""
    return bool(text and _ONLINE.search(text))
