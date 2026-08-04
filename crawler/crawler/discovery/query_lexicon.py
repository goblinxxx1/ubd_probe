"""LEARNED query lexicon (mirror of promo_lexicon): service/category terms that
feed build_grid as "{service} {audience}". Grown by the query miner + human audit;
structural categories seeded directly. Empty = byte-eq the static grid."""

import json

_learned: tuple[str, ...] = ()


def reload_learned(path: str | None) -> None:
    global _learned
    if not path:
        _learned = ()
        return
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        _learned = ()
        return
    entries = [e for e in data if isinstance(e, dict) and e.get("term")]
    cats = [e for e in entries if e.get("source") == "category"]
    rest = sorted((e for e in entries if e.get("source") != "category"),
                  key=lambda e: (-(e.get("z") or 0.0), e["term"]))
    seen: set[str] = set()
    out: list[str] = []
    for e in (*cats, *rest):
        key = e["term"].casefold()
        if key not in seen:
            seen.add(key)
            out.append(e["term"])
    _learned = tuple(out)


def learned_services() -> tuple[str, ...]:
    return _learned
