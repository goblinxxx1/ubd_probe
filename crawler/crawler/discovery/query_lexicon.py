"""LEARNED query lexicon (mirror of promo_lexicon): service/category terms that
feed build_grid as "{service} {audience}". Grown by the query miner + human audit;
structural categories seeded directly. Empty = byte-eq the static grid."""

import json

_cats: tuple[str, ...] = ()      # moderator-vetted structural categories (always in grid)
_mined: tuple[str, ...] = ()     # miner-learned service nouns, z-sorted (cap applies here only)


def reload_learned(path: str | None) -> None:
    global _cats, _mined
    if not path:
        _cats = _mined = ()
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        _cats = _mined = ()
        return
    if not isinstance(data, list):
        _cats = _mined = ()
        return
    entries = [e for e in data if isinstance(e, dict) and e.get("term")]
    cats = [e for e in entries if e.get("source") == "category"]
    rest = sorted((e for e in entries if e.get("source") != "category"),
                  key=lambda e: (-(e.get("z") or 0.0), e["term"]))
    seen: set[str] = set()
    cat_out: list[str] = []
    mined_out: list[str] = []
    for e in cats:
        key = e["term"].casefold()
        if key not in seen:
            seen.add(key)
            cat_out.append(e["term"])
    for e in rest:
        key = e["term"].casefold()
        if key not in seen:
            seen.add(key)
            mined_out.append(e["term"])
    _cats, _mined = tuple(cat_out), tuple(mined_out)


def learned_services() -> tuple[str, ...]:
    return _cats + _mined


def learned_services_split() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(category-sourced, miner-learned). Categories are always-in; only the mined
    tail is subject to the safety cap in compose_service_terms."""
    return _cats, _mined


def compose_service_terms(seed, cap: int) -> list[str]:
    """Grid service vocabulary: curated `seed` first (always), then learned
    categories (always), then miner terms. `cap<=0` = miner UNLIMITED (bounded only
    by audit quality) so self-learning never hits a ceiling; `cap>0` caps the MINED
    tail only — seed and categories are never dropped. Deduped case-insensitively."""
    mined = _mined if (cap is None or cap <= 0) else _mined[:cap]
    seen: set[str] = set()
    out: list[str] = []
    for term in (*seed, *_cats, *mined):
        key = (term or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(term)
    return out
