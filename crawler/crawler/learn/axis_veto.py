"""Terms that are grid AXES or generic noise — never a SERVICE, so the query miner must
not surface them as candidates. Lemmatized to match the miner's service_terms lemmas."""

from crawler.discovery.query_grid import AUDIENCE_FORMS, INTENT_FORMS, GRID_CITIES
from crawler.learn.tokenize import _lemma

# Generic / eligibility / geo nouns that recur in offers but are not services.
_NON_SERVICE = (
    "послуга", "вартість", "ціна", "пакет", "програма", "умова", "наявність",
    "участь", "право", "сила", "посвідчення", "документ", "знак", "повага",
    "вдячність", "захід", "служба", "центр", "година", "про",
    "україна", "дія", "місто", "область", "країна", "територія", "київ",
    # audience synonyms not spelled out in AUDIENCE_FORMS
    "переселенець", "оборона", "захисниця", "боєць", "герой",
)


def _lemmas_of(phrases) -> set[str]:
    out: set[str] = set()
    for phrase in phrases:
        for w in phrase.replace("’", "'").lower().split():
            lem = _lemma(w)
            if len(lem) >= 3:
                out.add(lem)
    return out


def axis_veto_terms() -> frozenset[str]:
    veto = _lemmas_of(AUDIENCE_FORMS) | _lemmas_of(INTENT_FORMS) | _lemmas_of(GRID_CITIES)
    veto |= {_lemma(w) for w in _NON_SERVICE}
    return frozenset(v for v in veto if v)


def is_axis_or_noise(term: str, veto: frozenset[str]) -> bool:
    """True if the whole term is vetoed, or (for a bigram) every word is vetoed."""
    if term in veto:
        return True
    words = term.split()
    return len(words) > 1 and all(w in veto for w in words)
